"""Contratos das métricas técnicas e das evidências do processo."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, generate_latest

from src.api.main import create_app
from src.observability.process_exporter import PipelineCollector


def _payload() -> dict:
    fixture = json.loads(open("tests/fixtures/golden_set.json", encoding="utf-8").read())
    return fixture["cases"][0]["request"]


def test_api_metrics_are_aggregatable_and_do_not_expose_identifiers(tmp_path) -> None:
    app = create_app(database_path=tmp_path / "serving.db")
    with TestClient(app) as client:
        decision = client.post("/v1/recommendations", json=_payload()).json()
        observed_at = (
            datetime.fromisoformat(decision["created_at"]) + timedelta(seconds=2)
        ).isoformat()
        client.post(
            "/v1/feedback",
            json={
                "recommendation_id": decision["recommendation_id"],
                "reward": 1,
                "observed_at": observed_at,
            },
        )
        metrics = client.get("/metrics").text

    assert 'route="/v1/recommendations"' in metrics
    assert "datathon_http_request_duration_seconds_bucket" in metrics
    expected_feedback = (
        'datathon_feedback_requests_total{learning_applied="false",reward="1",'
        'status="recorded"} 1.0'
    )
    assert expected_feedback in metrics
    assert "datathon_feedback_delay_seconds_bucket" in metrics
    assert "datathon_persisted_recommendations_total 1.0" in metrics
    expected_openfeature = (
        'datathon_openfeature_evaluations_total{requested_policy_mode="approved",'
        'source="static"} 1.0'
    )
    assert expected_openfeature in metrics
    assert "datathon_openfeature_configuration_version 1.0" in metrics
    assert decision["recommendation_id"] not in metrics


def test_pipeline_exporter_reads_only_versioned_aggregate_evidence() -> None:
    registry = CollectorRegistry(auto_describe=True)
    registry.register(PipelineCollector(project_root=Path.cwd()))

    metrics = generate_latest(registry).decode("utf-8")

    assert 'datathon_pipeline_artifact_available{artifact="model_report",stage="M3"} 1.0' in metrics
    assert 'datathon_pipeline_gate_passed{gate="candidate_policy"} 1.0' in metrics
    assert 'datathon_pipeline_gate_passed{gate="golden_set"} 1.0' in metrics
    assert 'metric="average_precision",model="logistic_propensity",split="test"' in metrics
