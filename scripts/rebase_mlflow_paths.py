"""Adapta as URIs de artefatos do MLflow ao diretório local do repositório."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    """Lê opções sem depender do diretório em que o comando foi executado."""
    parser = argparse.ArgumentParser(
        description=(
            "Adapta os caminhos absolutos do MLflow ao diretório deste clone "
            "sem alterar runs, parâmetros ou métricas."
        )
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("mlflow.db"),
        help="Banco SQLite do MLflow, relativo à raiz do projeto por padrão.",
    )
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=Path("mlruns"),
        help="Diretório de artefatos, relativo à raiz do projeto por padrão.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Apenas verifica as URIs; não modifica o banco.",
    )
    return parser.parse_args()


def resolve_project_path(path: Path) -> Path:
    """Resolve caminhos relativos a partir da raiz conhecida do projeto."""
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def expected_experiment_uri(artifacts_root: Path, experiment_id: str) -> str:
    """Monta a URI canônica do diretório de um experimento."""
    return (artifacts_root / experiment_id).as_uri()


def expected_run_uri(artifacts_root: Path, experiment_id: str, run_uuid: str) -> str:
    """Monta a URI canônica dos artefatos de uma execução."""
    return (artifacts_root / experiment_id / run_uuid / "artifacts").as_uri()


def validate_schema(connection: sqlite3.Connection) -> None:
    """Falha cedo quando o arquivo não possui o schema esperado do MLflow."""
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    missing_tables = {"experiments", "runs"} - tables
    if missing_tables:
        missing = ", ".join(sorted(missing_tables))
        raise RuntimeError(f"Banco sem tabelas obrigatórias do MLflow: {missing}")


def collect_mismatches(connection: sqlite3.Connection, artifacts_root: Path) -> list[str]:
    """Compara as URIs persistidas com os caminhos esperados neste clone."""
    mismatches: list[str] = []

    experiment_rows = connection.execute(
        "SELECT experiment_id, artifact_location FROM experiments"
    ).fetchall()
    for experiment_id, current_uri in experiment_rows:
        expected_uri = expected_experiment_uri(artifacts_root, str(experiment_id))
        if current_uri != expected_uri:
            mismatches.append(f"experimento {experiment_id}: {current_uri!r} != {expected_uri!r}")

    run_rows = connection.execute(
        "SELECT run_uuid, experiment_id, artifact_uri, lifecycle_stage FROM runs"
    ).fetchall()
    for run_uuid, experiment_id, current_uri, lifecycle_stage in run_rows:
        expected_uri = expected_run_uri(artifacts_root, str(experiment_id), str(run_uuid))
        if current_uri != expected_uri:
            mismatches.append(f"run {run_uuid}: {current_uri!r} != {expected_uri!r}")

        # Uma execução ativa deve apontar para um diretório compartilhado real.
        run_artifacts = artifacts_root / str(experiment_id) / str(run_uuid) / "artifacts"
        if lifecycle_stage != "deleted" and not run_artifacts.is_dir():
            mismatches.append(f"run {run_uuid}: diretório ausente em {run_artifacts}")

    return mismatches


def rebase_paths(connection: sqlite3.Connection, artifacts_root: Path) -> tuple[int, int]:
    """Atualiza somente os dois campos que carregam caminhos locais absolutos."""
    experiment_rows = connection.execute("SELECT experiment_id FROM experiments").fetchall()
    run_rows = connection.execute("SELECT run_uuid, experiment_id FROM runs").fetchall()

    with connection:
        for (experiment_id,) in experiment_rows:
            connection.execute(
                "UPDATE experiments SET artifact_location = ? WHERE experiment_id = ?",
                (
                    expected_experiment_uri(artifacts_root, str(experiment_id)),
                    experiment_id,
                ),
            )

        for run_uuid, experiment_id in run_rows:
            connection.execute(
                "UPDATE runs SET artifact_uri = ? WHERE run_uuid = ?",
                (
                    expected_run_uri(artifacts_root, str(experiment_id), str(run_uuid)),
                    run_uuid,
                ),
            )

    return len(experiment_rows), len(run_rows)


def main() -> int:
    """Executa adaptação idempotente e valida a integridade do SQLite."""
    args = parse_args()
    database_path = resolve_project_path(args.database)
    artifacts_root = resolve_project_path(args.artifacts_root)

    if not database_path.is_file():
        raise FileNotFoundError(f"Banco do MLflow não encontrado: {database_path}")
    if not artifacts_root.is_dir():
        raise FileNotFoundError(f"Diretório de artefatos não encontrado: {artifacts_root}")

    with sqlite3.connect(database_path) as connection:
        validate_schema(connection)

        if args.check_only:
            mismatches = collect_mismatches(connection, artifacts_root)
            if mismatches:
                print("As URIs do MLflow ainda não correspondem a este clone:")
                for mismatch in mismatches:
                    print(f"- {mismatch}")
                return 1
            print("URIs do MLflow e diretórios de artefatos estão consistentes.")
            return 0

        experiment_count, run_count = rebase_paths(connection, artifacts_root)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Falha de integridade do SQLite: {integrity}")

        mismatches = collect_mismatches(connection, artifacts_root)
        if mismatches:
            details = "\n".join(f"- {item}" for item in mismatches)
            raise RuntimeError(f"Falha ao validar caminhos adaptados:\n{details}")

    print(
        "Caminhos do MLflow adaptados com sucesso: "
        f"{experiment_count} experimento(s) e {run_count} run(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
