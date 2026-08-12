"""Configuração operacional avaliada por OpenFeature com fallback seguro."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
from dataclasses import dataclass
from typing import Protocol

from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider
from openfeature.evaluation_context import EvaluationContext

LOGGER = logging.getLogger("datathon.api.openfeature")


@dataclass(frozen=True)
class RuntimeConfiguration:
    """Snapshot tipado das flags que afetam uma decisão ou seu feedback."""

    version: int
    policy_mode: str
    kill_switch: bool
    adaptive_traffic_percentage: int
    experiment_name: str
    deterministic_allocation: bool
    learning_enabled: bool
    attribution_window_days: int
    structured_logs: bool
    decision_metrics: bool
    feedback_metrics: bool
    configuration_audit: bool
    trace_sampling_percentage: int
    source: str

    def allocates_adaptive(self, targeting_key: str) -> bool:
        """Aplica rollout percentual estável quando a alocação é determinística."""
        percentage = min(100, max(0, self.adaptive_traffic_percentage))
        if percentage <= 0:
            return False
        if percentage >= 100:
            return True
        if not self.deterministic_allocation:
            return random.SystemRandom().randrange(100) < percentage
        allocation_key = f"{self.experiment_name}:{targeting_key}".encode("utf-8")
        bucket = int.from_bytes(hashlib.sha256(allocation_key).digest()[:8], "big") % 100
        return bucket < percentage


class RuntimeConfigurationProvider(Protocol):
    """Contrato pequeno para permitir testes sem rede e troca de provider."""

    def resolve(self, targeting_key: str) -> RuntimeConfiguration:
        """Resolve um snapshot para a oportunidade informada."""


class StaticRuntimeConfigurationProvider:
    """Provider seguro usado em testes, CLI e quando OpenFeature está desligado."""

    def __init__(self, configuration: RuntimeConfiguration) -> None:
        self.configuration = configuration

    def resolve(self, targeting_key: str) -> RuntimeConfiguration:  # noqa: ARG002
        return self.configuration


class OpenFeatureRuntimeConfigurationProvider:
    """Avalia as flags remotamente no flagd por meio do SDK OpenFeature."""

    def __init__(self, fallback: RuntimeConfiguration) -> None:
        self.fallback = fallback
        api.set_provider(FlagdProvider())
        self.client = api.get_client(domain="datathon-serving")

    def resolve(self, targeting_key: str) -> RuntimeConfiguration:
        context = EvaluationContext(
            targeting_key=targeting_key,
            attributes={"service": "recommendation-api"},
        )
        fallback = self.fallback
        evaluations = {
            "version": self.client.get_integer_details(
                "configuration-version", fallback.version, context
            ),
            "policy_mode": self.client.get_string_details(
                "policy-mode", fallback.policy_mode, context
            ),
            "kill_switch": self.client.get_boolean_details(
                "kill-switch", fallback.kill_switch, context
            ),
            "adaptive_traffic_percentage": self.client.get_integer_details(
                "adaptive-traffic-percentage",
                fallback.adaptive_traffic_percentage,
                context,
            ),
            "experiment_name": self.client.get_string_details(
                "experiment-name", fallback.experiment_name, context
            ),
            "deterministic_allocation": self.client.get_boolean_details(
                "deterministic-allocation", fallback.deterministic_allocation, context
            ),
            "learning_enabled": self.client.get_boolean_details(
                "learning-enabled", fallback.learning_enabled, context
            ),
            "attribution_window_days": self.client.get_integer_details(
                "attribution-window-days", fallback.attribution_window_days, context
            ),
            "structured_logs": self.client.get_boolean_details(
                "structured-logs", fallback.structured_logs, context
            ),
            "decision_metrics": self.client.get_boolean_details(
                "decision-metrics", fallback.decision_metrics, context
            ),
            "feedback_metrics": self.client.get_boolean_details(
                "feedback-metrics", fallback.feedback_metrics, context
            ),
            "configuration_audit": self.client.get_boolean_details(
                "configuration-audit", fallback.configuration_audit, context
            ),
            "trace_sampling_percentage": self.client.get_integer_details(
                "trace-sampling-percentage", fallback.trace_sampling_percentage, context
            ),
        }
        has_error = any(getattr(detail, "error_code", None) for detail in evaluations.values())
        source = "fallback" if has_error else "flagd"
        if has_error:
            LOGGER.warning(
                "Uma ou mais flags não puderam ser avaliadas; defaults seguros foram usados.",
                extra={
                    "event": "openfeature_fallback",
                    "targeting_key_hash": _hash_key(targeting_key),
                },
            )
        policy_mode = str(evaluations["policy_mode"].value)
        if policy_mode not in {"approved", "approved_adaptive", "adaptive_demo"}:
            policy_mode = fallback.policy_mode
            source = "fallback"
        return RuntimeConfiguration(
            version=max(1, int(evaluations["version"].value)),
            policy_mode=policy_mode,
            kill_switch=bool(evaluations["kill_switch"].value),
            adaptive_traffic_percentage=_bounded_int(
                evaluations["adaptive_traffic_percentage"].value, 0, 100
            ),
            experiment_name=str(evaluations["experiment_name"].value),
            deterministic_allocation=bool(evaluations["deterministic_allocation"].value),
            learning_enabled=bool(evaluations["learning_enabled"].value),
            attribution_window_days=_bounded_int(
                evaluations["attribution_window_days"].value, 1, 30
            ),
            structured_logs=bool(evaluations["structured_logs"].value),
            decision_metrics=bool(evaluations["decision_metrics"].value),
            feedback_metrics=bool(evaluations["feedback_metrics"].value),
            configuration_audit=bool(evaluations["configuration_audit"].value),
            trace_sampling_percentage=_bounded_int(
                evaluations["trace_sampling_percentage"].value, 0, 100
            ),
            source=source,
        )


def build_runtime_configuration_provider(
    *,
    default_policy_mode: str,
    attribution_window_days: int,
) -> RuntimeConfigurationProvider:
    """Habilita flagd apenas quando solicitado explicitamente pelo ambiente."""
    fallback = RuntimeConfiguration(
        version=1,
        policy_mode=default_policy_mode,
        kill_switch=False,
        adaptive_traffic_percentage=100 if default_policy_mode != "approved" else 0,
        experiment_name="explicit-runtime" if default_policy_mode != "approved" else "",
        deterministic_allocation=True,
        learning_enabled=default_policy_mode != "approved",
        attribution_window_days=attribution_window_days,
        structured_logs=True,
        decision_metrics=True,
        feedback_metrics=True,
        configuration_audit=True,
        trace_sampling_percentage=10,
        source="static",
    )
    enabled = os.getenv("OPENFEATURE_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if enabled:
        return OpenFeatureRuntimeConfigurationProvider(fallback)
    return StaticRuntimeConfigurationProvider(fallback)


def fallback_targeting_key(context: dict[str, object]) -> str:
    """Cria uma chave estável sem armazenar o contexto integral nas flags."""
    canonical = json.dumps(context, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return f"context-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]}"


def _bounded_int(value: object, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return minimum
    return min(maximum, max(minimum, parsed))


def _hash_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
