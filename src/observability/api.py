"""Métricas, logs estruturados e tracing da API FastAPI."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from prometheus_client.gc_collector import GCCollector
from prometheus_client.platform_collector import PlatformCollector
from prometheus_client.process_collector import ProcessCollector

LOGGER = logging.getLogger("datathon.observability")
_SQLITE_INSTRUMENTED = False


def _trace_context() -> dict[str, str]:
    """Retorna identificadores do span ativo sem criar cardinalidade em métricas."""
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return {}
    return {
        "trace_id": f"{context.trace_id:032x}",
        "span_id": f"{context.span_id:016x}",
    }


class JsonFormatter(logging.Formatter):
    """Serializa eventos operacionais em JSON para ingestão no Loki."""

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", None)
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": event or "log",
            "message": record.getMessage(),
        }
        fields = getattr(record, "event_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        trace_fields = {
            key: value for key, value in _trace_context().items() if key not in payload
        }
        payload.update(trace_fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str, log_file: str | None = None) -> None:
    """Configura uma única cadeia JSON para todos os loggers ``datathon.*``."""
    logger = logging.getLogger("datathon")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = JsonFormatter()
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    selected_log_file = log_file or os.getenv("DATATHON_LOG_FILE")
    if selected_log_file:
        path = Path(selected_log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            path,
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Emite evento estruturado sem interpolar payloads de clientes."""
    logger.info(event, extra={"event": event, "event_fields": fields})


def route_template(request: Request) -> str:
    """Normaliza rotas parametrizadas e limita a cardinalidade das séries."""
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str):
        return route_path
    if request.url.path in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}:
        return request.url.path
    return "__unmatched__"


class RepositoryMetricsCollector:
    """Expõe contadores persistidos no SQLite em vez de duplicá-los na memória."""

    def __init__(self, counts: Callable[[], dict[str, int | float]]) -> None:
        self._counts = counts

    def collect(self):  # type: ignore[no-untyped-def]
        success = GaugeMetricFamily(
            "datathon_repository_scrape_success",
            "1 quando os agregados persistidos puderam ser consultados.",
        )
        try:
            counts = self._counts()
        except Exception:  # noqa: BLE001 - o scrape técnico deve continuar disponível.
            success.add_metric([], 0)
            LOGGER.exception("Falha ao coletar métricas persistidas do SQLite.")
            yield success
            return

        success.add_metric([], 1)
        yield success
        families = (
            (
                "datathon_persisted_recommendations_total",
                "Recomendações persistidas desde a criação do banco.",
                counts["recommendations"],
            ),
            (
                "datathon_persisted_feedback_total",
                "Feedbacks terminais persistidos desde a criação do banco.",
                counts["feedback"],
            ),
            (
                "datathon_observed_reward_total",
                "Soma persistida das recompensas observadas.",
                counts["observed_reward_total"],
            ),
            (
                "datathon_learning_applied_total",
                "Feedbacks persistidos que atualizaram a política adaptativa.",
                counts["learning_applied"],
            ),
        )
        for name, documentation, value in families:
            metric = CounterMetricFamily(name, documentation, value=float(value))
            yield metric

        reward_mean = GaugeMetricFamily(
            "datathon_observed_reward_mean",
            "Média persistida de recompensa; use total/feedback para agregação.",
            value=float(counts["observed_reward_mean"]),
        )
        yield reward_mean


class ServiceMetrics:
    """Registro Prometheus isolado por instância da aplicação."""

    LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
    FEEDBACK_DELAY_BUCKETS = (1, 5, 30, 60, 300, 1800, 3600, 21600, 86400, 604800)

    def __init__(self, repository_counts: Callable[[], dict[str, int | float]]) -> None:
        self.registry = CollectorRegistry(auto_describe=True)
        ProcessCollector(registry=self.registry)
        PlatformCollector(registry=self.registry)
        GCCollector(registry=self.registry)
        self.registry.register(RepositoryMetricsCollector(repository_counts))

        self.http_requests = Counter(
            "datathon_http_requests_total",
            "Requisições HTTP concluídas por método, rota normalizada e classe de status.",
            ("method", "route", "status_class"),
            registry=self.registry,
        )
        self.http_duration = Histogram(
            "datathon_http_request_duration_seconds",
            "Duração das requisições HTTP em segundos.",
            ("method", "route"),
            buckets=self.LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.http_in_flight = Gauge(
            "datathon_http_requests_in_flight",
            "Requisições HTTP atualmente em processamento.",
            registry=self.registry,
        )
        self.recommendations = Counter(
            "datathon_recommendations_total",
            "Recomendações emitidas por ação e política.",
            ("action", "policy_id", "policy_version", "policy_mode"),
            registry=self.registry,
        )
        self.explorations = Counter(
            "datathon_explorations_total",
            "Recomendações exploratórias emitidas.",
            ("action", "policy_version"),
            registry=self.registry,
        )
        self.fallbacks = Counter(
            "datathon_fallbacks_total",
            "Recomendações que precisaram usar um braço elegível alternativo.",
            ("action", "policy_version"),
            registry=self.registry,
        )
        self.feedback = Counter(
            "datathon_feedback_requests_total",
            "Feedbacks aceitos pela API, incluindo duplicatas idempotentes.",
            ("status", "reward", "learning_applied"),
            registry=self.registry,
        )
        self.feedback_delay = Histogram(
            "datathon_feedback_delay_seconds",
            "Tempo entre a recomendação e a observação do feedback.",
            buckets=self.FEEDBACK_DELAY_BUCKETS,
            registry=self.registry,
        )
        self.domain_errors = Counter(
            "datathon_domain_errors_total",
            "Erros de domínio por operação e motivo canônico.",
            ("operation", "reason"),
            registry=self.registry,
        )
        self.ready = Gauge(
            "datathon_service_ready",
            "1 quando política, modelo e armazenamento estão prontos.",
            registry=self.registry,
        )
        self.policy_info = Gauge(
            "datathon_policy_info",
            "Metadados de baixa cardinalidade da política carregada.",
            ("policy_id", "policy_version", "policy_mode", "model_version"),
            registry=self.registry,
        )

    def set_policy_info(
        self,
        *,
        policy_id: str | None,
        policy_version: str | None,
        policy_mode: str | None,
        model_version: str | None,
    ) -> None:
        self.policy_info.labels(
            policy_id=policy_id or "unavailable",
            policy_version=policy_version or "unavailable",
            policy_mode=policy_mode or "unavailable",
            model_version=model_version or "unavailable",
        ).set(1)

    def observe_request(
        self, *, method: str, route: str, status_code: int, latency_seconds: float
    ) -> None:
        status_class = f"{status_code // 100}xx"
        self.http_requests.labels(method=method, route=route, status_class=status_class).inc()
        self.http_duration.labels(method=method, route=route).observe(latency_seconds)

    def observe_recommendation(
        self,
        *,
        action: str,
        policy_id: str,
        policy_version: str,
        policy_mode: str,
        exploration: bool,
        fallback: bool,
    ) -> None:
        self.recommendations.labels(
            action=action,
            policy_id=policy_id,
            policy_version=policy_version,
            policy_mode=policy_mode,
        ).inc()
        if exploration:
            self.explorations.labels(action=action, policy_version=policy_version).inc()
        if fallback:
            self.fallbacks.labels(action=action, policy_version=policy_version).inc()

    def observe_feedback(
        self,
        *,
        result_status: str,
        reward: int,
        learning_applied: bool,
        delay_seconds: float,
    ) -> None:
        self.feedback.labels(
            status=result_status,
            reward=str(reward),
            learning_applied=str(learning_applied).lower(),
        ).inc()
        if result_status == "recorded":
            self.feedback_delay.observe(max(delay_seconds, 0.0))

    def observe_domain_error(self, operation: str, reason: str) -> None:
        self.domain_errors.labels(operation=operation, reason=reason).inc()


def configure_tracing(app: FastAPI, service_name: str, service_version: str) -> bool:
    """Envia traces OTLP somente quando um Collector foi configurado."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return False

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
            "deployment.environment.name": os.getenv("DEPLOYMENT_ENVIRONMENT", "local"),
        }
    )
    provider = TracerProvider(resource=resource)
    insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() in {
        "1",
        "true",
        "yes",
    }
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls=r".*/metrics,.*/health",
    )

    global _SQLITE_INSTRUMENTED
    if not _SQLITE_INSTRUMENTED:
        SQLite3Instrumentor().instrument(tracer_provider=provider)
        _SQLITE_INSTRUMENTED = True
    app.state.tracer_provider = provider
    return True
