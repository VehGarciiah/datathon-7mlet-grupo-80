"""Política Thompson Sampling Beta-Bernoulli com fallback global."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.data.contracts import DataContractError
from src.features.build_features import ACTION_COLUMN, TARGET_COLUMN
from src.policies.base import Decision


@dataclass
class BetaPosterior:
    """Armazena os parâmetros suficientes de uma distribuição Beta."""

    alpha: float
    beta: float

    @property
    def mean(self) -> float:
        """Retorna a média posterior da recompensa Bernoulli."""
        return self.alpha / (self.alpha + self.beta)

    def update(self, reward: int) -> None:
        """Aplica uma única recompensa binária ao posterior."""
        self.alpha += reward
        self.beta += 1 - reward


def _json_scalar(value: Any) -> Any:
    """Converte escalares NumPy/Pandas em valores JSON estáveis."""
    if pd.isna(value):
        return "__ausente__"
    if isinstance(value, np.generic):
        return value.item()
    return value


class SegmentedThompsonSamplingPolicy:
    """Seleciona braços por amostras Beta e aprende apenas com feedback observado."""

    def __init__(
        self,
        action_order: list[str],
        *,
        segment_columns: list[str],
        minimum_support_per_action: int,
        prior_alpha: float = 1.0,
        prior_beta: float = 1.0,
        random_seed: int = 42,
        policy_id: str = "segmented_thompson_sampling",
        version: str = "1.0.0",
        historical_reward_warm_start: bool = False,
    ) -> None:
        if not action_order or len(set(action_order)) != len(action_order):
            raise DataContractError("A ordem de ações deve ser não vazia e sem duplicatas.")
        if not segment_columns or len(set(segment_columns)) != len(segment_columns):
            raise DataContractError("As colunas de segmento devem ser não vazias e únicas.")
        if minimum_support_per_action <= 0:
            raise DataContractError("O suporte mínimo por ação deve ser positivo.")
        if prior_alpha <= 0 or prior_beta <= 0:
            raise DataContractError("Os parâmetros do prior Beta devem ser positivos.")

        self.action_order = tuple(action_order)
        self.segment_columns = tuple(segment_columns)
        self.minimum_support_per_action = minimum_support_per_action
        self.prior_alpha = float(prior_alpha)
        self.prior_beta = float(prior_beta)
        self.random_seed = int(random_seed)
        self.policy_id = policy_id
        self.version = version
        self.historical_reward_warm_start = historical_reward_warm_start
        self.global_posteriors = self._new_action_posteriors()
        self.segment_posteriors: dict[str, dict[str, BetaPosterior]] = {}
        self.segment_support: dict[str, dict[str, int]] = {}
        self.processed_feedback_ids: set[str] = set()
        self.rng = np.random.default_rng(self.random_seed)
        self.is_fitted = False

    def _new_action_posteriors(self) -> dict[str, BetaPosterior]:
        """Cria um conjunto independente de priors para todos os braços."""
        return {
            action: BetaPosterior(self.prior_alpha, self.prior_beta) for action in self.action_order
        }

    def _segment_id_from_context(self, context: dict) -> str:
        """Produz chave sem ambiguidade a partir do contexto pré-decisão."""
        missing = [column for column in self.segment_columns if column not in context]
        if missing:
            raise DataContractError(f"Contexto sem colunas de segmento: {missing}.")
        values = [_json_scalar(context[column]) for column in self.segment_columns]
        return json.dumps(values, ensure_ascii=False, separators=(",", ":"))

    def fit_support(self, frame: pd.DataFrame) -> "SegmentedThompsonSamplingPolicy":
        """Define segmentos suportados no treino sem usar recompensa por padrão."""
        required = {ACTION_COLUMN, TARGET_COLUMN, *self.segment_columns}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise DataContractError(f"Colunas ausentes para ajustar a política: {missing}.")
        unexpected_actions = sorted(set(frame[ACTION_COLUMN]) - set(self.action_order))
        if unexpected_actions:
            raise DataContractError(f"Ações fora do contrato: {unexpected_actions}.")
        if not set(frame[TARGET_COLUMN]).issubset({0, 1}):
            raise DataContractError("A recompensa da política deve ser binária.")

        self.global_posteriors = self._new_action_posteriors()
        self.segment_posteriors = {}
        self.segment_support = {}
        self.processed_feedback_ids = set()
        self.rng = np.random.default_rng(self.random_seed)

        if self.historical_reward_warm_start:
            for action in self.action_order:
                rewards = frame.loc[frame[ACTION_COLUMN].eq(action), TARGET_COLUMN]
                self.global_posteriors[action].alpha += int(rewards.sum())
                self.global_posteriors[action].beta += int(len(rewards) - rewards.sum())

        grouped = frame.groupby(list(self.segment_columns), dropna=False, sort=True)
        for segment_values, segment_frame in grouped:
            values = segment_values if isinstance(segment_values, tuple) else (segment_values,)
            segment_id = json.dumps(
                [_json_scalar(value) for value in values],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            support = {
                action: int(segment_frame[ACTION_COLUMN].eq(action).sum())
                for action in self.action_order
            }
            self.segment_support[segment_id] = support
            if min(support.values()) < self.minimum_support_per_action:
                continue

            posteriors = self._new_action_posteriors()
            if self.historical_reward_warm_start:
                for action in self.action_order:
                    rewards = segment_frame.loc[
                        segment_frame[ACTION_COLUMN].eq(action), TARGET_COLUMN
                    ]
                    posteriors[action].alpha += int(rewards.sum())
                    posteriors[action].beta += int(len(rewards) - rewards.sum())
            self.segment_posteriors[segment_id] = posteriors

        self.is_fitted = True
        return self

    def _posterior_source(self, context: dict) -> tuple[str, dict[str, BetaPosterior], bool]:
        """Seleciona posterior segmentado ou fallback global de forma auditável."""
        segment_id = self._segment_id_from_context(context)
        if segment_id in self.segment_posteriors:
            return segment_id, self.segment_posteriors[segment_id], False
        return segment_id, self.global_posteriors, True

    def recommend(self, context: dict, eligible_actions: list[str]) -> Decision:
        """Amostra cada braço elegível e retorna a maior realização Beta."""
        if not self.is_fitted:
            raise DataContractError("A política adaptativa ainda não foi ajustada.")
        unknown = sorted(set(eligible_actions) - set(self.action_order))
        if unknown:
            raise DataContractError(f"Ações elegíveis fora do contrato: {unknown}.")
        allowed_actions = [action for action in self.action_order if action in eligible_actions]
        if not allowed_actions:
            raise DataContractError("Nenhuma ação elegível foi fornecida.")

        segment_id, posteriors, sparse_fallback = self._posterior_source(context)
        posterior_means = {action: posteriors[action].mean for action in self.action_order}
        samples = {
            action: float(self.rng.beta(posteriors[action].alpha, posteriors[action].beta))
            for action in allowed_actions
        }
        preferred_action = max(
            self.action_order,
            key=lambda action: (posterior_means[action], -self.action_order.index(action)),
        )
        preferred_eligible_action = max(
            allowed_actions,
            key=lambda action: (posterior_means[action], -self.action_order.index(action)),
        )
        selected_action = max(
            allowed_actions,
            key=lambda action: (samples[action], -self.action_order.index(action)),
        )
        used_fallback = preferred_action not in allowed_actions
        is_exploration = selected_action != preferred_eligible_action
        source = "posterior global" if sparse_fallback else "posterior do segmento"

        return Decision(
            action=selected_action,
            policy_id=self.policy_id,
            policy_version=self.version,
            is_exploration=is_exploration,
            used_fallback=used_fallback or sparse_fallback,
            reason=f"Thompson Sampling usando {source} e somente ações elegíveis.",
            details={
                "segment_id": segment_id,
                "posterior_source": "global" if sparse_fallback else "segment",
                "samples": samples,
                "posterior_means": posterior_means,
            },
        )

    def update(
        self,
        action: str,
        reward: int,
        context: dict,
        *,
        feedback_id: str | None = None,
    ) -> bool:
        """Atualiza o braço factual uma vez no global e no segmento suportado."""
        if not self.is_fitted:
            raise DataContractError("A política adaptativa ainda não foi ajustada.")
        if action not in self.action_order:
            raise DataContractError(f"Ação fora do contrato: {action}.")
        if reward not in {0, 1}:
            raise DataContractError("A recompensa deve ser 0 ou 1.")
        if feedback_id is not None and feedback_id in self.processed_feedback_ids:
            return False

        segment_id = self._segment_id_from_context(context)
        self.global_posteriors[action].update(reward)
        if segment_id in self.segment_posteriors:
            self.segment_posteriors[segment_id][action].update(reward)
        if feedback_id is not None:
            self.processed_feedback_ids.add(feedback_id)
        return True

    def clone_with_seed(self, random_seed: int) -> "SegmentedThompsonSamplingPolicy":
        """Copia o estado inicial e troca apenas o gerador estocástico."""
        clone = copy.deepcopy(self)
        clone.random_seed = int(random_seed)
        clone.rng = np.random.default_rng(clone.random_seed)
        clone.processed_feedback_ids = set()
        return clone

    def to_dict(self) -> dict[str, Any]:
        """Serializa estado, suporte e configuração para reprodução."""
        if not self.is_fitted:
            raise DataContractError("A política adaptativa ainda não foi ajustada.")
        return {
            "schema_version": "1.0.0",
            "policy_id": self.policy_id,
            "policy_version": self.version,
            "action_order": list(self.action_order),
            "segment_columns": list(self.segment_columns),
            "minimum_support_per_action": self.minimum_support_per_action,
            "prior": {"alpha": self.prior_alpha, "beta": self.prior_beta},
            "historical_reward_warm_start": self.historical_reward_warm_start,
            "random_seed": self.random_seed,
            "rng_state": self.rng.bit_generator.state,
            "global_posteriors": {
                action: asdict(posterior) for action, posterior in self.global_posteriors.items()
            },
            "segment_posteriors": {
                segment_id: {action: asdict(posterior) for action, posterior in posteriors.items()}
                for segment_id, posteriors in self.segment_posteriors.items()
            },
            "segment_support": self.segment_support,
            "processed_feedback_ids": sorted(self.processed_feedback_ids),
        }

    @classmethod
    def load_state(cls, path: str | Path) -> "SegmentedThompsonSamplingPolicy":
        """Restaura posterior, suporte, feedbacks e sequência aleatória persistidos."""
        content = json.loads(Path(path).read_text(encoding="utf-8"))
        if content.get("schema_version") != "1.0.0":
            raise DataContractError("Versão de estado da política não suportada.")
        policy = cls(
            content["action_order"],
            segment_columns=content["segment_columns"],
            minimum_support_per_action=int(content["minimum_support_per_action"]),
            prior_alpha=float(content["prior"]["alpha"]),
            prior_beta=float(content["prior"]["beta"]),
            random_seed=int(content["random_seed"]),
            policy_id=content["policy_id"],
            version=content["policy_version"],
            historical_reward_warm_start=bool(content["historical_reward_warm_start"]),
        )
        policy.global_posteriors = {
            action: BetaPosterior(**parameters)
            for action, parameters in content["global_posteriors"].items()
        }
        policy.segment_posteriors = {
            segment_id: {
                action: BetaPosterior(**parameters) for action, parameters in posteriors.items()
            }
            for segment_id, posteriors in content["segment_posteriors"].items()
        }
        policy.segment_support = {
            segment_id: {action: int(count) for action, count in support.items()}
            for segment_id, support in content["segment_support"].items()
        }
        policy.processed_feedback_ids = set(content["processed_feedback_ids"])
        policy.rng.bit_generator.state = content["rng_state"]
        policy.is_fitted = True
        return policy

    def save_state(self, path: str | Path) -> Path:
        """Persiste JSON por substituição atômica no mesmo sistema de arquivos."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"
        temporary_path: Path | None = None
        try:
            # Um temporário exclusivo evita colisão entre persistências concorrentes.
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=destination.parent,
                delete=False,
            ) as temporary_file:
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
                temporary_path = Path(temporary_file.name)
            os.replace(temporary_path, destination)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
        return destination
