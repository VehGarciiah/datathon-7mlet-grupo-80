"""Testes dos guardrails do rollout controlado por OpenFeature."""

from __future__ import annotations

from dataclasses import replace

from src.api.feature_flags import RuntimeConfiguration


def _configuration(**changes: object) -> RuntimeConfiguration:
    configuration = RuntimeConfiguration(
        version=1,
        policy_mode="adaptive_demo",
        kill_switch=False,
        adaptive_traffic_percentage=25,
        experiment_name="demo-openfeature",
        deterministic_allocation=True,
        learning_enabled=True,
        attribution_window_days=7,
        structured_logs=True,
        decision_metrics=True,
        feedback_metrics=True,
        configuration_audit=True,
        trace_sampling_percentage=10,
        source="flagd",
    )
    return replace(configuration, **changes)


def test_deterministic_rollout_keeps_the_same_opportunity_in_the_same_group() -> None:
    configuration = _configuration()

    allocations = [configuration.allocates_adaptive("OP-000123") for _ in range(20)]

    assert len(set(allocations)) == 1


def test_rollout_boundaries_are_explicit() -> None:
    assert _configuration(adaptive_traffic_percentage=0).allocates_adaptive("OP-000123") is False
    assert _configuration(adaptive_traffic_percentage=100).allocates_adaptive("OP-000123") is True
