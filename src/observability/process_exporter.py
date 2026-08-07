"""Exportador Prometheus das evidências versionadas do pipeline de ML."""

from __future__ import annotations

import json
import os
import signal
import threading
from pathlib import Path
from typing import Any

from prometheus_client.core import GaugeMetricFamily
from prometheus_client.exposition import start_http_server
from prometheus_client.registry import CollectorRegistry

ARTIFACTS = (
    ("M1", "interim_metadata", "data/interim/bank_marketing_ptbr.metadata.json"),
    ("M2", "preparation_metadata", "data/processed/preparation.metadata.json"),
    ("M2", "train_split", "data/processed/train.csv"),
    ("M2", "validation_split", "data/processed/validation.csv"),
    ("M2", "test_split", "data/processed/test.csv"),
    ("M3", "propensity_model", "artifacts/models/propensity_pipeline.joblib"),
    ("M3", "model_report", "reports/modeling/m3_metrics.json"),
    ("M4", "adaptive_policy", "artifacts/policies/thompson_policy_state.json"),
    ("M4", "policy_report", "reports/policy/m4_policy_evaluation.json"),
    ("M5", "golden_set_report", "reports/serving/golden_set_results.json"),
)


def _read_json(path: Path) -> dict[str, Any]:
    content = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise ValueError(f"JSON não mapeável: {path}")
    return content


class PipelineCollector:
    """Converte apenas métricas agregadas e gates conhecidos em séries estáveis."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def collect(self):  # type: ignore[no-untyped-def]
        available = GaugeMetricFamily(
            "datathon_pipeline_artifact_available",
            "1 quando a evidência versionada está disponível.",
            labels=("stage", "artifact"),
        )
        modified = GaugeMetricFamily(
            "datathon_pipeline_artifact_mtime_seconds",
            "Última modificação da evidência em Unix timestamp.",
            labels=("stage", "artifact"),
        )
        for stage, artifact, relative_path in ARTIFACTS:
            path = self.project_root / relative_path
            exists = path.is_file()
            available.add_metric((stage, artifact), 1 if exists else 0)
            if exists:
                modified.add_metric((stage, artifact), path.stat().st_mtime)
        yield available
        yield modified

        model_report = self.project_root / "reports/modeling/m3_metrics.json"
        model_success = GaugeMetricFamily(
            "datathon_pipeline_source_read_success",
            "1 quando o relatório pôde ser interpretado.",
            labels=("source",),
        )
        model_metric = GaugeMetricFamily(
            "datathon_model_evaluation_metric",
            "Métrica offline do modelo de propensão.",
            labels=("model", "split", "metric"),
        )
        try:
            model = _read_json(model_report)
            logistic = model["predictive_models"]["logistic_regression"]
            for split in ("validation", "test"):
                for metric in ("average_precision", "brier_score", "roc_auc"):
                    model_metric.add_metric(
                        ("logistic_propensity", split, metric),
                        float(logistic[split][metric]),
                    )
            model_success.add_metric(("m3_model_report",), 1)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            model_success.add_metric(("m3_model_report",), 0)
        yield model_metric

        policy_report = self.project_root / "reports/policy/m4_policy_evaluation.json"
        policy_metric = GaugeMetricFamily(
            "datathon_policy_evaluation_metric",
            "Métrica offline de replay por política e split.",
            labels=("policy", "split", "metric"),
        )
        candidate_gate = GaugeMetricFamily(
            "datathon_pipeline_gate_passed",
            "1 quando o gate técnico versionado foi aprovado.",
            labels=("gate",),
        )
        try:
            policy = _read_json(policy_report)
            for split in ("validation", "test"):
                split_result = policy["splits"][split]
                fixed = split_result["fixed_baseline"]
                adaptive = split_result["adaptive_policy"]
                policy_metric.add_metric(
                    ("fixed_baseline", split, "mean_reward"), float(fixed["mean_reward"])
                )
                policy_metric.add_metric(
                    ("fixed_baseline", split, "replay_coverage"),
                    float(fixed["replay_coverage"]),
                )
                policy_metric.add_metric(
                    ("adaptive_policy", split, "mean_reward"),
                    float(adaptive["mean_reward"]["mean"]),
                )
                policy_metric.add_metric(
                    ("adaptive_policy", split, "replay_coverage"),
                    float(adaptive["replay_coverage"]["mean"]),
                )
                policy_metric.add_metric(
                    ("adaptive_policy", split, "absolute_lift"),
                    float(adaptive["lift_vs_fixed"]["absolute_mean"]),
                )
            candidate_gate.add_metric(
                ("candidate_policy",),
                1 if policy["selection"]["candidate_gate_passed"] else 0,
            )
            model_success.add_metric(("m4_policy_report",), 1)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            candidate_gate.add_metric(("candidate_policy",), 0)
            model_success.add_metric(("m4_policy_report",), 0)
        yield policy_metric

        golden_report = self.project_root / "reports/serving/golden_set_results.json"
        golden = GaugeMetricFamily(
            "datathon_golden_set_cases",
            "Casos do golden set por resultado.",
            labels=("result",),
        )
        try:
            golden_result = _read_json(golden_report)
            golden.add_metric(("passed",), float(golden_result["passed_count"]))
            golden.add_metric(
                ("failed",),
                float(golden_result["case_count"] - golden_result["passed_count"]),
            )
            candidate_gate.add_metric(
                ("golden_set",), 1 if golden_result["all_cases_passed"] else 0
            )
            model_success.add_metric(("m5_golden_set_report",), 1)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            candidate_gate.add_metric(("golden_set",), 0)
            model_success.add_metric(("m5_golden_set_report",), 0)
        yield golden
        yield candidate_gate
        yield model_success


def main() -> int:
    """Inicia endpoint HTTP e aguarda encerramento cooperativo do container."""
    project_root = Path(os.getenv("DATATHON_PROJECT_ROOT", ".")).resolve()
    port = int(os.getenv("DATATHON_PROCESS_EXPORTER_PORT", "9101"))
    registry = CollectorRegistry(auto_describe=True)
    registry.register(PipelineCollector(project_root))
    start_http_server(port, addr="0.0.0.0", registry=registry)

    stopped = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    stopped.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
