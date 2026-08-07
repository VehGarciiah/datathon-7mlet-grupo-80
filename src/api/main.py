"""Aplicação FastAPI com serving seguro, feedback e observabilidade local."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

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
from src.observability.api import (
    ServiceMetrics,
    configure_logging,
    configure_tracing,
    log_event,
    route_template,
)

LOGGER = logging.getLogger("datathon.api")


def create_app(
    config_path: str | Path = "configs/api.yaml",
    *,
    config_override: APIConfig | None = None,
    database_path: str | Path | None = None,
    policy_mode: str | None = None,
) -> FastAPI:
    """Cria aplicação injetável para produção local e testes isolados."""
    config = config_override or load_api_config(config_path)
    configure_logging(config.log_level)
    service = RecommendationService(
        config,
        database_path=database_path,
        policy_mode=policy_mode,
    )
    metrics = ServiceMetrics(service.repository.counts)
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
    readiness = service.readiness()
    metrics.ready.set(1 if readiness.status == "ready" else 0)
    metrics.set_policy_info(
        policy_id=readiness.active_policy_id,
        policy_version=readiness.active_policy_version,
        policy_mode=readiness.policy_mode,
        model_version=readiness.model_version,
    )

    @app.middleware("http")
    async def observe_http(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Mede e registra requisições sem inspecionar o corpo."""
        started_at = time.perf_counter()
        status_code = 500
        should_observe = request.url.path != "/metrics"
        if should_observe:
            metrics.http_in_flight.inc()
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            latency = time.perf_counter() - started_at
            if should_observe:
                route = route_template(request)
                metrics.observe_request(
                    method=request.method,
                    route=route,
                    status_code=status_code,
                    latency_seconds=latency,
                )
                metrics.http_in_flight.dec()
                log_event(
                    LOGGER,
                    "http_request",
                    method=request.method,
                    route=route,
                    status=status_code,
                    status_class=f"{status_code // 100}xx",
                    latency_ms=round(latency * 1000, 3),
                    policy_version=(
                        getattr(service.active_policy, "version", None)
                        if service.active_policy
                        else None
                    ),
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
        current_readiness = service.readiness()
        if not service.repository.integrity_check():
            current_readiness = current_readiness.model_copy(
                update={"status": "not_ready", "error": "Falha de integridade do SQLite."}
            )
        if current_readiness.status != "ready":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        metrics.ready.set(1 if current_readiness.status == "ready" else 0)
        return current_readiness

    @app.get("/metrics", include_in_schema=False)
    def prometheus_metrics() -> Response:
        """Expõe o registro Prometheus sem payloads ou identificadores."""
        return Response(content=generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)

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
            metrics.observe_domain_error("recommendation", "ineligible")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except ServiceNotReadyError as exc:
            metrics.observe_domain_error("recommendation", "service_not_ready")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc
        metrics.observe_recommendation(
            action=result.recommended_action.value,
            policy_id=result.policy_id,
            policy_version=result.policy_version,
            policy_mode=str(result.evidence["policy_mode"]),
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
            metrics.observe_domain_error("feedback", "recommendation_not_found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="recommendation_id não encontrado.",
            ) from exc
        except ConflictingFeedbackError as exc:
            metrics.observe_domain_error("feedback", "conflicting_terminal_feedback")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Feedback terminal conflitante já registrado.",
            ) from exc
        except InvalidFeedbackTimeError as exc:
            metrics.observe_domain_error("feedback", "invalid_observation_time")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        except ServiceNotReadyError as exc:
            metrics.observe_domain_error("feedback", "service_not_ready")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
            ) from exc

        recommendation = service.repository.get_recommendation(str(payload.recommendation_id))
        delay_seconds = (
            (payload.observed_at - recommendation.created_at).total_seconds()
            if recommendation is not None
            else 0.0
        )
        metrics.observe_feedback(
            result_status=result.status,
            reward=payload.reward,
            learning_applied=result.learning_applied,
            delay_seconds=delay_seconds,
        )
        return result

    configure_tracing(app, config.service_name, app.version)
    return app


app = create_app()
