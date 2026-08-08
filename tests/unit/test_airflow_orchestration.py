"""Contratos do DAG e do profile local de orquestração."""

from __future__ import annotations

import ast
from pathlib import Path

import yaml


def test_airflow_dag_keeps_the_four_existing_modules_in_order() -> None:
    dag_path = Path("orchestration/dags/datathon_pipeline.py")
    source = dag_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    modules = [
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_run_module"
        and isinstance(node.args[0], ast.Constant)
    ]

    assert modules == [
        "src.data.translate",
        "src.data.prepare",
        "src.models.train_propensity",
        "src.evaluation.replay",
    ]
    assert "translate() >> prepare() >> train() >> evaluate()" in source
    assert "schedule=None" in source
    assert "max_active_runs=1" in source


def test_airflow_is_an_optional_compose_profile_with_mlflow_dependency() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    airflow = compose["services"]["airflow"]

    assert airflow["profiles"] == ["orchestration"]
    assert airflow["command"] == ["standalone"]
    assert airflow["environment"]["AIRFLOW__CORE__EXECUTOR"] == "LocalExecutor"
    assert airflow["environment"]["MLFLOW_TRACKING_URI"] == "http://mlflow:5000"
    assert airflow["depends_on"]["mlflow"]["condition"] == "service_healthy"
    assert "airflow-data:/opt/airflow" in airflow["volumes"]
