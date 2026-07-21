"""Aplicação FastAPI com serving seguro, feedback e observabilidade local."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse

from src.api.repository import ConflictingFeedbackError, RecommendationNotFoundError
from src.api.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    ReadyResponse,
    RecommendationRequest,
    RecommendationResponse,
)
from src.api.service import (
    APIConfig,
    EligibilityError,
    InvalidFeedbackTimeError,
    RecommendationService,
    ServiceNotReadyError,
    load_api_config,
)

LOGGER = logging.getLogger("datathon.api")


class ServiceMetrics:
    """Mantém contadores técnicos agregados sem payloads de clientes."""

    def __init__(self, history_limit: int) -> None:
        self.lock = threading.Lock()
        self.requests: dict[tuple[str, int], int] = defaultdict(int)
        self.latencies: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=history_limit))
        self.recommendations = 0
        self.feedback = 0
        self.explorations = 0
        self.fallbacks = 0

    def observe_request(self, path: str, status_code: int, latency_seconds: float) -> None:
        """Registra volume, código e latência por rota."""
        with self.lock:
            self.requests[(path, status_code)] += 1
            self.latencies[path].append(latency_seconds)

    def observe_recommendation(self, *, exploration: bool, fallback: bool) -> None:
        """Agrega decisões sem guardar contexto ou identificador."""
        with self.lock:
            self.recommendations += 1
            self.explorations += int(exploration)
            self.fallbacks += int(fallback)

    def observe_feedback(self) -> None:
        """Incrementa feedbacks HTTP aceitos, inclusive duplicados seguros."""
        with self.lock:
            self.feedback += 1

    def render_prometheus(self, repository_counts: dict[str, int | float]) -> str:
        """Renderiza subconjunto Prometheus sem dependência adicional."""
        with self.lock:
            lines = [
                "# HELP datathon_http_requests_total Requisições HTTP por rota e status.",
                "# TYPE datathon_http_requests_total counter",
            ]
            for (path, status_code), count in sorted(self.requests.items()):
                lines.append(
                    f'datathon_http_requests_total{{path="{path}",status="{status_code}"}} {count}'
                )
            lines.extend(
                [
                    "# HELP datathon_recommendations_total Recomendações emitidas.",
                    "# TYPE datathon_recommendations_total counter",
                    f"datathon_recommendations_total {self.recommendations}",
                    f"datathon_feedback_requests_total {self.feedback}",
                    f"datathon_explorations_total {self.explorations}",
                    f"datathon_fallbacks_total {self.fallbacks}",
                    f"datathon_persisted_recommendations {repository_counts['recommendations']}",
                    f"datathon_persisted_feedback {repository_counts['feedback']}",
                    f"datathon_observed_reward_total {repository_counts['observed_reward_total']}",
                    f"datathon_observed_reward_mean {repository_counts['observed_reward_mean']}",
                    f"datathon_learning_applied_total {repository_counts['learning_applied']}",
                ]
            )
            for path, values in sorted(self.latencies.items()):
                if values:
                    ordered = sorted(values)
                    index = min(len(ordered) - 1, int(0.95 * len(ordered)))
                    lines.append(
                        f'datathon_http_latency_p95_seconds{{path="{path}"}} {ordered[index]:.6f}'
                    )
        return "\n".join(lines) + "\n"


def create_app(
    config_path: str | Path = "configs/api.yaml",
    *,
    config_override: APIConfig | None = None,
    database_path: str | Path | None = None,
    policy_mode: str | None = None,
) -> FastAPI:
    """Cria aplicação injetável para produção local e testes isolados."""
    config = config_override or load_api_config(config_path)
    logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO))
    service = RecommendationService(
        config,
        database_path=database_path,
        policy_mode=policy_mode,
    )
    metrics = ServiceMetrics(config.metrics_history_limit)
    app = FastAPI(
        title="Datathon — Próximo melhor canal",
        version="1.0.0",
        description=(
            "API educacional. A recomendação seleciona canal elegível e não representa "
            "decisão financeira nem inferência causal."
        ),
    )
    app.state.service = service
    app.state.metrics = metrics

    @app.middleware("http")
    async def observe_http(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Emite log estruturado sem corpo da requisição."""
        started_at = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            latency = time.perf_counter() - started_at
            metrics.observe_request(request.url.path, status_code, latency)
            LOGGER.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "method": request.method,
                        "path": request.url.path,
                        "status": status_code,
                        "latency_ms": round(latency * 1000, 3),
                        "policy_version": (
                            getattr(service.active_policy, "version", None)
                            if service.active_policy
                            else None
                        ),
                    },
                    ensure_ascii=False,
                )
            )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """Confirma apenas que o processo HTTP está vivo."""
        return HealthResponse(
            status="alive",
            service=config.service_name,
            timestamp=datetime.now(timezone.utc),
        )

    @app.get("/ready", response_model=ReadyResponse)
    def ready(response: Response) -> ReadyResponse:
        """Confirma política, modelo, SQLite e linhagem MLflow carregados."""
        readiness = service.readiness()
        if not service.repository.integrity_check():
            readiness = readiness.model_copy(
                update={"status": "not_ready", "error": "Falha de integridade do SQLite."}
            )
        if readiness.status != "ready":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return readiness

    @app.get("/metrics", response_class=PlainTextResponse)
    def prometheus_metrics() -> str:
        """Expõe somente contadores e latências agregadas."""
        return metrics.render_prometheus(service.repository.counts())

    @app.post(
        "/v1/recommendations",
        response_model=RecommendationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def recommend(payload: RecommendationRequest) -> RecommendationResponse:
        """Emite decisão elegível e auditável."""
        try:
            result = service.recommend(payload)
        except EligibilityError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except ServiceNotReadyError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
        metrics.observe_recommendation(
            exploration=result.is_exploration,
            fallback=result.used_fallback,
        )
        return result

    @app.post("/v1/feedback", response_model=FeedbackResponse)
    def feedback(payload: FeedbackRequest) -> FeedbackResponse:
        """Registra feedback terminal de modo idempotente."""
        try:
            result = service.record_feedback(payload)
        except RecommendationNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="recommendation_id não encontrado.",
            ) from exc
        except ConflictingFeedbackError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Feedback terminal conflitante já registrado.",
            ) from exc
        except InvalidFeedbackTimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        except ServiceNotReadyError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
        metrics.observe_feedback()
        return result

    return app


app = create_app()
