"""Testes de contrato, golden set e segurança operacional da API."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api.feature_flags import RuntimeConfiguration, StaticRuntimeConfigurationProvider
from src.api.main import create_app
from src.api.service import load_api_config
from src.evaluation.golden_set import run_golden_set


def _golden_payload() -> dict:
    """Reutiliza o primeiro payload sintético versionado."""
    fixture = json.loads(open("tests/fixtures/golden_set.json", encoding="utf-8").read())
    return fixture["cases"][0]["request"]


def test_golden_set_processes_exactly_five_reviewed_cases(tmp_path) -> None:
    """Confirma ações, versões, fallback e revisão humana pela API real."""
    report = run_golden_set("configs/api.yaml", database_path=tmp_path / "golden.db")
    assert report["case_count"] == 5
    assert report["passed_count"] == 5
    assert report["all_cases_passed"] is True
    assert all(case["human_review"]["status"] for case in report["cases"])
    assert all(case["audit_context_used_by_policy"] is False for case in report["cases"])


def test_recommendation_feedback_idempotency_and_metrics(tmp_path) -> None:
    """Cobre decisão, feedback novo, duplicado, conflitante e métricas agregadas."""
    app = create_app(database_path=tmp_path / "serving.db")
    with TestClient(app) as client:
        ready = client.get("/ready")
        assert ready.status_code == 200
        assert ready.json()["policy_mode"] == "approved_fixed_rollback"

        recommendation = client.post("/v1/recommendations", json=_golden_payload())
        assert recommendation.status_code == 201
        decision = recommendation.json()
        assert decision["recommended_action"] == "celular"
        assert decision["evidence"]["causal_claim"] is False
        observed_at = (
            datetime.fromisoformat(decision["created_at"]) + timedelta(seconds=1)
        ).isoformat()
        feedback = {
            "recommendation_id": decision["recommendation_id"],
            "reward": 1,
            "observed_at": observed_at,
        }

        first = client.post("/v1/feedback", json=feedback)
        duplicate = client.post("/v1/feedback", json=feedback)
        conflict = client.post("/v1/feedback", json={**feedback, "reward": 0})
        missing = client.post(
            "/v1/feedback",
            json={**feedback, "recommendation_id": str(uuid4())},
        )
        metrics = client.get("/metrics")

    assert first.status_code == 200
    assert first.json()["status"] == "recorded"
    assert first.json()["learning_applied"] is False
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"
    assert conflict.status_code == 409
    assert missing.status_code == 404
    assert 'datathon_recommendations_total{action="celular"' in metrics.text
    assert "datathon_persisted_feedback_total 1.0" in metrics.text
    assert "datathon_http_request_duration_seconds_bucket" in metrics.text


def test_schema_and_eligibility_errors_are_explicit(tmp_path) -> None:
    """Bloqueia faixa inválida, campo extra, contato proibido e lista vazia."""
    app = create_app(database_path=tmp_path / "serving.db")
    payload = _golden_payload()
    with TestClient(app) as client:
        invalid_range = json.loads(json.dumps(payload))
        invalid_range["context"]["euribor_3_meses"] = 99
        assert client.post("/v1/recommendations", json=invalid_range).status_code == 422

        extra_audit_field = json.loads(json.dumps(payload))
        extra_audit_field["context"]["profissao"] = "desconhecido"
        assert client.post("/v1/recommendations", json=extra_audit_field).status_code == 422

        unauthorized = {**payload, "contact_authorized": False}
        assert client.post("/v1/recommendations", json=unauthorized).status_code == 409

        no_actions = {**payload, "eligible_actions": []}
        assert client.post("/v1/recommendations", json=no_actions).status_code == 422


def test_missing_adaptive_state_falls_back_and_missing_fixed_blocks_ready(tmp_path) -> None:
    """Aplica rollback no adaptativo ausente e 503 sem baseline obrigatório."""
    config = load_api_config("configs/api.yaml")
    missing_adaptive = replace(
        config,
        adaptive_initial_state_path=tmp_path / "missing-adaptive.json",
        adaptive_runtime_state_path=tmp_path / "runtime.json",
    )
    fallback_app = create_app(
        config_override=missing_adaptive,
        database_path=tmp_path / "fallback.db",
        policy_mode=config.adaptive_demo_mode,
    )
    with TestClient(fallback_app) as client:
        readiness = client.get("/ready")
        assert readiness.status_code == 200
        assert readiness.json()["policy_mode"] == "approved_fixed_rollback"
        assert "rollback fixo" in readiness.json()["fallback_reason"]

    missing_fixed = replace(
        config,
        fixed_policy_artifact_path=tmp_path / "missing-fixed.joblib",
    )
    blocked_app = create_app(
        config_override=missing_fixed,
        database_path=tmp_path / "blocked.db",
    )
    with TestClient(blocked_app) as client:
        assert client.get("/ready").status_code == 503
        assert client.post("/v1/recommendations", json=_golden_payload()).status_code == 503


def test_adaptive_demo_updates_only_explicit_runtime_state(tmp_path) -> None:
    """Permite aprendizado apenas no modo demonstrativo solicitado explicitamente."""
    config = load_api_config("configs/api.yaml")
    demo_config = replace(
        config,
        adaptive_runtime_state_path=tmp_path / "thompson-runtime.json",
    )
    app = create_app(
        config_override=demo_config,
        database_path=tmp_path / "adaptive.db",
        policy_mode=config.adaptive_demo_mode,
    )
    with TestClient(app) as client:
        ready = client.get("/ready")
        assert ready.json()["policy_mode"] == "adaptive_demo"
        recommendation = client.post("/v1/recommendations", json=_golden_payload()).json()
        feedback = client.post(
            "/v1/feedback",
            json={
                "recommendation_id": recommendation["recommendation_id"],
                "reward": 1,
                "observed_at": (
                    datetime.fromisoformat(recommendation["created_at"]) + timedelta(seconds=1)
                ).isoformat(),
            },
        )
    assert feedback.status_code == 200
    assert feedback.json()["learning_applied"] is True
    assert demo_config.adaptive_runtime_state_path.exists()


def test_openfeature_kill_switch_forces_the_approved_baseline(tmp_path) -> None:
    runtime = RuntimeConfiguration(
        version=9,
        policy_mode="adaptive_demo",
        kill_switch=True,
        adaptive_traffic_percentage=100,
        experiment_name="kill-switch-test",
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
    app = create_app(
        database_path=tmp_path / "kill-switch.db",
        runtime_configuration_provider=StaticRuntimeConfigurationProvider(runtime),
    )

    with TestClient(app) as client:
        decision = client.post("/v1/recommendations", json=_golden_payload()).json()

    assert decision["policy_id"] == "best_historical_action"
    assert decision["evidence"]["policy_mode"] == "approved_fixed_kill_switch"
    assert decision["evidence"]["openfeature"]["configuration_version"] == 9
    assert decision["evidence"]["openfeature"]["fallback_reason"] == "kill_switch"
