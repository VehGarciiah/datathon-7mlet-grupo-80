"""DAG visual do pipeline reproduzível M1–M4 do Datathon."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from airflow.sdk import dag, task

PROJECT_ROOT = Path(os.getenv("DATATHON_PROJECT_ROOT", "/workspace"))


def _run_module(module: str, config_path: str) -> None:
    """Executa o módulo existente e encaminha sua saída ao log da tarefa."""
    subprocess.run(
        (sys.executable, "-m", module, "--config", config_path),
        cwd=PROJECT_ROOT,
        check=True,
    )


@dag(
    dag_id="datathon_pipeline_m1_m4",
    description="Traduz dados, prepara splits, treina o baseline e avalia a política.",
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    default_args={
        "owner": "datathon-grupo-80",
        "retries": 1,
        "retry_delay": timedelta(minutes=1),
    },
    tags=["datathon", "mle", "mlflow", "manual"],
    doc_md="""
    Pipeline acadêmico M1–M4. A lógica permanece nos módulos de `src/`;
    este DAG controla somente dependências, tentativas, estado e logs.
    """,
)
def datathon_pipeline():
    @task(task_id="m1_traduzir_e_validar", execution_timeout=timedelta(minutes=10))
    def translate() -> None:
        _run_module("src.data.translate", "configs/data.yaml")

    @task(task_id="m2_preparar_splits", execution_timeout=timedelta(minutes=15))
    def prepare() -> None:
        _run_module("src.data.prepare", "configs/data.yaml")

    @task(task_id="m3_treinar_baselines", execution_timeout=timedelta(minutes=30))
    def train() -> None:
        _run_module("src.models.train_propensity", "configs/modeling.yaml")

    @task(task_id="m4_avaliar_politica", execution_timeout=timedelta(minutes=45))
    def evaluate() -> None:
        _run_module("src.evaluation.replay", "configs/policy.yaml")

    translate() >> prepare() >> train() >> evaluate()


datathon_pipeline()
