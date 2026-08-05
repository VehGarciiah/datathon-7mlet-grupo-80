"""Carregamento seguro de artefatos e ciclo de decisão/feedback."""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import joblib
import yaml

from src.api.repository import (
    ConflictingFeedbackError,
    FeedbackRecord,
    RecommendationNotFoundError,
    RecommendationRecord,
    SQLiteServingRepository,
)
from src.api.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    ReadyResponse,
    RecommendationRequest,
    RecommendationResponse,
)
from src.data.contracts import DataContractError
from src.policies.thompson_sampling import SegmentedThompsonSamplingPolicy

LOGGER = logging.getLogger("datathon.api")


class EligibilityError(RuntimeError):
    """Indica oportunidade que exige abstenção da política."""


class ServiceNotReadyError(RuntimeError):
    """Indica que nenhum rollback seguro pôde ser carregado."""


class InvalidFeedbackTimeError(ValueError):
    """Indica timestamp incompatível com a decisão registrada."""


@dataclass(frozen=True)
class APIConfig:
    """Agrupa caminhos e controles operacionais do M5."""

    project_root: Path
    config_path: Path
    experiment_config_path: Path
    modeling_config_path: Path
    policy_config_path: Path
    adaptive_segment_columns: tuple[str, ...]
    selection_strategy: str
    default_policy_mode: str
    approved_adaptive_mode: str
    adaptive_demo_mode: str
    adaptive_demo_enabled: bool
    policy_mode_environment_variable: str
    fixed_policy_artifact_path: Path
    adaptive_initial_state_path: Path
    adaptive_runtime_state_path: Path
    propensity_model_artifact_path: Path
    m4_evaluation_path: Path
    m3_latest_run_path: Path
    m4_latest_run_path: Path
    database_path: Path
    sqlite_timeout_seconds: float
    attribution_window_days: int
    accept_future_clock_skew_seconds: int
    golden_fixture_path: Path
    golden_results_path: Path
    service_name: str
    metrics_history_limit: int
    log_level: str


def _read_yaml(path: Path) -> dict[str, Any]:
    """Carrega configuração YAML mapeável."""
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise DataContractError(f"Configuração inválida ou vazia: {path}.")
    return content


def load_api_config(config_path: str | Path = "configs/api.yaml") -> APIConfig:
    """Resolve todos os caminhos relativamente à raiz do projeto."""
    resolved_path = Path(config_path).resolve()
    project_root = resolved_path.parent.parent
    content = _read_yaml(resolved_path)
    policy_config_path = project_root / content["policy_config_path"]
    policy_content = _read_yaml(policy_config_path)
    adaptive_segment_columns = tuple(policy_content["adaptive_policy"]["segmentation"]["columns"])
    if not adaptive_segment_columns:
        raise DataContractError("A política adaptativa deve declarar colunas de segmento.")
    serving = content["serving"]
    storage = content["storage"]
    feedback = content["feedback"]
    golden = content["golden_set"]
    observability = content["observability"]
    return APIConfig(
        project_root=project_root,
        config_path=resolved_path,
        experiment_config_path=project_root / content["experiment_config_path"],
        modeling_config_path=project_root / content["modeling_config_path"],
        policy_config_path=policy_config_path,
        adaptive_segment_columns=adaptive_segment_columns,
        selection_strategy=serving["selection_strategy"],
        default_policy_mode=serving["default_policy_mode"],
        approved_adaptive_mode=serving["approved_adaptive_mode"],
        adaptive_demo_mode=serving["adaptive_demo_mode"],
        adaptive_demo_enabled=bool(serving["adaptive_demo_enabled"]),
        policy_mode_environment_variable=serving["policy_mode_environment_variable"],
        fixed_policy_artifact_path=project_root / serving["fixed_policy_artifact_path"],
        adaptive_initial_state_path=project_root / serving["adaptive_initial_state_path"],
        adaptive_runtime_state_path=project_root / serving["adaptive_runtime_state_path"],
        propensity_model_artifact_path=project_root / serving["propensity_model_artifact_path"],
        m4_evaluation_path=project_root / serving["m4_evaluation_path"],
        m3_latest_run_path=project_root / serving["m3_latest_run_path"],
        m4_latest_run_path=project_root / serving["m4_latest_run_path"],
        database_path=project_root / storage["database_path"],
        sqlite_timeout_seconds=float(storage["sqlite_timeout_seconds"]),
        attribution_window_days=int(feedback["attribution_window_days"]),
        accept_future_clock_skew_seconds=int(feedback["accept_future_clock_skew_seconds"]),
        golden_fixture_path=project_root / golden["fixture_path"],
        golden_results_path=project_root / golden["results_path"],
        service_name=observability["service_name"],
        metrics_history_limit=int(observability["metrics_history_limit"]),
        log_level=observability["log_level"],
    )


def _read_json_if_available(path: Path) -> dict[str, Any]:
    """Retorna metadados opcionais sem impedir o fallback aprovado."""
    if not path.is_file():
        return {}
    content = json.loads(path.read_text(encoding="utf-8"))
    return content if isinstance(content, dict) else {}


class RecommendationService:
    """Coordena políticas, persistência mínima e atribuição de recompensa."""

    def __init__(
        self,
        config: APIConfig,
        *,
        database_path: str | Path | None = None,
        policy_mode: str | None = None,
    ) -> None:
        self.config = config
        selected_database = (
            Path(database_path) if database_path is not None else config.database_path
        )
        self.repository = SQLiteServingRepository(
            selected_database,
            timeout_seconds=config.sqlite_timeout_seconds,
        )
        self.lock = threading.RLock()
        self.is_ready = False
        self.load_error: str | None = None
        self.fallback_reason: str | None = None
        self.active_policy: Any | None = None
        self.active_policy_mode: str | None = None
        self.model_version: str | None = None
        self.m3_run_id = _read_json_if_available(config.m3_latest_run_path).get("run_id")
        self.m4_run_id = _read_json_if_available(config.m4_latest_run_path).get("run_id")
        requested_mode = (
            policy_mode
            or os.getenv(config.policy_mode_environment_variable)
            or config.default_policy_mode
        )
        self._load_artifacts(requested_mode)

    def _load_fixed_policy(self) -> Any:
        """Carrega a política de rollback aprovada e valida sua estrutura."""
        artifact = joblib.load(self.config.fixed_policy_artifact_path)
        policy = artifact.get("policy") if isinstance(artifact, dict) else None
        if policy is None or getattr(policy, "best_action", None) is None:
            raise DataContractError("Artefato da política fixa inválido.")
        return policy

    def _load_model_version(self) -> str:
        """Carrega apenas metadado do modelo sem usá-lo como política causal."""
        artifact = joblib.load(self.config.propensity_model_artifact_path)
        if not isinstance(artifact, dict) or "model_version" not in artifact:
            raise DataContractError("Artefato do modelo de propensão inválido.")
        return str(artifact["model_version"])

    def _load_adaptive_demo(self) -> SegmentedThompsonSamplingPolicy:
        """Restaura estado de demonstração isolado do artefato inicial."""
        runtime_path = self.config.adaptive_runtime_state_path
        if not runtime_path.exists():
            runtime_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.config.adaptive_initial_state_path, runtime_path)
        return SegmentedThompsonSamplingPolicy.load_state(runtime_path)

    def _load_artifacts(self, requested_mode: str) -> None:
        """Resolve política aprovada e sempre prioriza rollback seguro."""
        try:
            fixed_policy = self._load_fixed_policy()
            self.model_version = self._load_model_version()
        except Exception as exc:  # noqa: BLE001 - converte falha de artefato em readiness segura.
            LOGGER.exception("Falha ao carregar artefatos obrigatórios do serving.")
            self.load_error = f"Artefato obrigatório indisponível: {type(exc).__name__}."
            return

        m4_report = _read_json_if_available(self.config.m4_evaluation_path)
        adaptive_status = m4_report.get("selection", {}).get("status")
        if requested_mode == self.config.adaptive_demo_mode:
            if not self.config.adaptive_demo_enabled:
                self.fallback_reason = "Modo adaptativo demonstrativo desabilitado."
            else:
                try:
                    self.active_policy = self._load_adaptive_demo()
                    self.active_policy_mode = self.config.adaptive_demo_mode
                    self.is_ready = True
                    self.fallback_reason = (
                        "Modo demonstrativo explícito; política não aprovada para promoção."
                    )
                    return
                except Exception as exc:  # noqa: BLE001 - fallback é requisito operacional.
                    LOGGER.exception("Falha no estado adaptativo; aplicando rollback fixo.")
                    self.fallback_reason = (
                        "Estado adaptativo indisponível; rollback fixo aplicado "
                        f"({type(exc).__name__})."
                    )
        elif adaptive_status == "approved":
            try:
                self.active_policy = self._load_adaptive_demo()
                self.active_policy_mode = self.config.approved_adaptive_mode
                self.is_ready = True
                return
            except Exception as exc:  # noqa: BLE001 - rollback é requisito operacional.
                LOGGER.exception("Falha no estado adaptativo aprovado; aplicando rollback.")
                self.fallback_reason = (
                    "Estado adaptativo aprovado indisponível; rollback fixo aplicado "
                    f"({type(exc).__name__})."
                )
        elif adaptive_status != "approved":
            self.fallback_reason = (
                f"Política adaptativa com status {adaptive_status or 'desconhecido'}; "
                "rollback fixo mantido."
            )

        self.active_policy = fixed_policy
        self.active_policy_mode = "approved_fixed_rollback"
        self.is_ready = True

    def readiness(self) -> ReadyResponse:
        """Resume carregamento sem revelar caminhos internos."""
        return ReadyResponse(
            status="ready" if self.is_ready else "not_ready",
            active_policy_id=(
                getattr(self.active_policy, "policy_id", None) if self.active_policy else None
            ),
            active_policy_version=(
                getattr(self.active_policy, "version", None) if self.active_policy else None
            ),
            policy_mode=self.active_policy_mode,
            model_version=self.model_version,
            m3_run_id=self.m3_run_id,
            m4_run_id=self.m4_run_id,
            fallback_reason=self.fallback_reason,
            error=self.load_error,
        )

    def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        """Valida elegibilidade, decide e registra somente contexto mínimo."""
        if not self.is_ready or self.active_policy is None or self.model_version is None:
            raise ServiceNotReadyError("Serviço sem política de rollback carregada.")
        if not request.contact_authorized:
            raise EligibilityError("Contato não autorizado; revisão humana obrigatória.")
        if request.do_not_contact:
            raise EligibilityError("Cliente em regra de não contato; política deve se abster.")

        context = request.context.model_dump(mode="json")
        eligible_actions = [action.value for action in request.eligible_actions]
        with self.lock:
            decision = self.active_policy.recommend(context, eligible_actions)
            recommendation_id = str(uuid4())
            created_at = datetime.now(timezone.utc)
            learning_context = {
                column: context[column] for column in self.config.adaptive_segment_columns
            }
            record = RecommendationRecord(
                recommendation_id=recommendation_id,
                created_at=created_at,
                recommended_action=decision.action,
                policy_id=decision.policy_id,
                policy_version=decision.policy_version,
                policy_mode=str(self.active_policy_mode),
                model_version=self.model_version,
                is_exploration=decision.is_exploration,
                used_fallback=decision.used_fallback,
                reason=decision.reason,
                learning_context=learning_context,
                eligible_actions=eligible_actions,
            )
            self.repository.save_recommendation(record)

        evidence: dict[str, Any] = {
            "policy_mode": self.active_policy_mode,
            "causal_claim": False,
            "uses_audit_only_attributes": False,
        }
        if decision.details:
            evidence.update(decision.details)
        else:
            evidence["rule"] = "best_historical_action_from_train"
        return RecommendationResponse(
            recommendation_id=recommendation_id,
            recommended_action=decision.action,
            policy_id=decision.policy_id,
            policy_version=decision.policy_version,
            model_version=self.model_version,
            is_exploration=decision.is_exploration,
            used_fallback=decision.used_fallback,
            reason=decision.reason,
            evidence=evidence,
            created_at=created_at,
        )

    def record_feedback(self, request: FeedbackRequest) -> FeedbackResponse:
        """Registra recompensa uma vez e atualiza apenas demonstração adaptativa válida."""
        if not self.is_ready:
            raise ServiceNotReadyError("Serviço sem política carregada.")
        recommendation_id = str(request.recommendation_id)
        observed_at = request.observed_at.astimezone(timezone.utc)
        received_at = datetime.now(timezone.utc)

        with self.lock:
            recommendation = self.repository.get_recommendation(recommendation_id)
            if recommendation is None:
                raise RecommendationNotFoundError(recommendation_id)
            existing = self.repository.get_feedback(recommendation_id)
            if existing is not None:
                if existing.reward != request.reward or existing.observed_at != observed_at:
                    raise ConflictingFeedbackError(recommendation_id)
                return FeedbackResponse(
                    recommendation_id=recommendation_id,
                    status="duplicate",
                    learning_applied=existing.learning_applied,
                    reason="Feedback idêntico já havia sido registrado; nenhuma nova atualização.",
                )

            maximum_future = received_at + timedelta(
                seconds=self.config.accept_future_clock_skew_seconds
            )
            if observed_at < recommendation.created_at:
                raise InvalidFeedbackTimeError("Feedback não pode anteceder a recomendação.")
            if observed_at > maximum_future:
                raise InvalidFeedbackTimeError(
                    "Feedback está além da tolerância de relógio futura."
                )

            deadline = recommendation.created_at + timedelta(
                days=self.config.attribution_window_days
            )
            learning_applied = False
            if observed_at > deadline:
                learning_reason = (
                    "Feedback tardio preservado para auditoria, sem aprendizado automático."
                )
            elif (
                recommendation.policy_mode
                in {
                    self.config.adaptive_demo_mode,
                    self.config.approved_adaptive_mode,
                }
                and self.active_policy_mode == recommendation.policy_mode
                and isinstance(self.active_policy, SegmentedThompsonSamplingPolicy)
            ):
                learning_applied = self.active_policy.update(
                    recommendation.recommended_action,
                    request.reward,
                    recommendation.learning_context,
                    feedback_id=recommendation_id,
                )
                self.active_policy.save_state(self.config.adaptive_runtime_state_path)
                learning_reason = (
                    "Posterior demonstrativo atualizado somente para o braço recomendado."
                )
            else:
                learning_reason = (
                    "Política fixa aprovada não possui atualização online; "
                    "feedback apenas auditado."
                )

            feedback = FeedbackRecord(
                recommendation_id=recommendation_id,
                reward=request.reward,
                observed_at=observed_at,
                received_at=received_at,
                learning_applied=learning_applied,
                learning_reason=learning_reason,
            )
            _, inserted = self.repository.save_feedback(feedback)
            if not inserted:
                raise RuntimeError("Concorrência inesperada fora do lock do serviço.")

        return FeedbackResponse(
            recommendation_id=recommendation_id,
            status="recorded",
            learning_applied=learning_applied,
            reason=learning_reason,
        )
