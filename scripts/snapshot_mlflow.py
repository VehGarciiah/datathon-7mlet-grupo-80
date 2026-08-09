"""Publica e valida um snapshot reproduzível do MLflow usado no Compose."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from scripts.rebase_mlflow_paths import rebase_paths, validate_schema

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCES = (
    Path("reports/modeling/latest_mlflow_run.json"),
    Path("reports/policy/latest_mlflow_run.json"),
)
ACTIVE_RUN_STATUSES = {"RUNNING", "SCHEDULED"}


@dataclass(frozen=True)
class SnapshotSummary:
    """Contagens publicadas no snapshot versionado."""

    run_count: int
    artifact_file_count: int
    reference_count: int


def parse_args() -> argparse.Namespace:
    """Lê os caminhos da origem em volume e do snapshot no checkout."""
    parser = argparse.ArgumentParser(
        description=(
            "Copia de forma consistente o SQLite e os artefatos do volume MLflow "
            "para o snapshot versionado do projeto."
        )
    )
    parser.add_argument("--source-database", type=Path, default=Path("/mlflow/mlflow.db"))
    parser.add_argument("--source-artifacts", type=Path, default=Path("/mlflow/mlruns"))
    parser.add_argument("--destination-database", type=Path, default=Path("mlflow.db"))
    parser.add_argument("--destination-artifacts", type=Path, default=Path("mlruns"))
    parser.add_argument(
        "--canonical-artifacts-root",
        type=Path,
        default=Path("/mlflow/mlruns"),
        help="Raiz persistida nas URIs do snapshot; o entrypoint a adapta ao iniciar.",
    )
    parser.add_argument(
        "--reference",
        type=Path,
        action="append",
        dest="references",
        help="JSON com experiment_id e run_id que deve existir no snapshot.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Valida o snapshot de destino sem copiar o volume.",
    )
    return parser.parse_args()


def _resolved(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _active_runs(database_path: Path) -> list[str]:
    with closing(sqlite3.connect(database_path)) as connection:
        validate_schema(connection)
        placeholders = ",".join("?" for _ in ACTIVE_RUN_STATUSES)
        rows = connection.execute(
            f"SELECT run_uuid FROM runs WHERE status IN ({placeholders})",  # noqa: S608
            tuple(sorted(ACTIVE_RUN_STATUSES)),
        ).fetchall()
    return [str(row[0]) for row in rows]


def _copy_artifacts(source: Path, destination: Path) -> int:
    if not source.is_dir():
        raise FileNotFoundError(f"Diretório de artefatos do volume não encontrado: {source}")
    if source == destination:
        raise ValueError("Origem e destino de artefatos devem ser diferentes.")

    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True, copy_function=shutil.copy2)
    return sum(path.is_file() for path in destination.rglob("*"))


def _backup_database(source: Path, destination: Path, canonical_root: Path) -> int:
    if not source.is_file():
        raise FileNotFoundError(f"Banco do volume MLflow não encontrado: {source}")
    if source == destination:
        raise ValueError("Origem e destino do banco devem ser diferentes.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=".mlflow-snapshot-",
        suffix=".db",
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)

    try:
        with closing(sqlite3.connect(source)) as source_connection:
            validate_schema(source_connection)
            with closing(sqlite3.connect(temporary_path)) as destination_connection:
                source_connection.backup(destination_connection)
                rebase_paths(destination_connection, canonical_root)
                integrity = destination_connection.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    raise RuntimeError(f"Falha de integridade do snapshot SQLite: {integrity}")
                run_count = int(
                    destination_connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
                )
        os.replace(temporary_path, destination)
        return run_count
    finally:
        temporary_path.unlink(missing_ok=True)


def validate_snapshot(
    database_path: Path,
    artifacts_root: Path,
    references: tuple[Path, ...],
) -> SnapshotSummary:
    """Confirma integridade, runs finais e artefatos referenciados por M3/M4."""
    if not database_path.is_file():
        raise FileNotFoundError(f"Snapshot SQLite não encontrado: {database_path}")
    if not artifacts_root.is_dir():
        raise FileNotFoundError(f"Snapshot de artefatos não encontrado: {artifacts_root}")

    artifact_file_count = sum(path.is_file() for path in artifacts_root.rglob("*"))
    with closing(sqlite3.connect(database_path)) as connection:
        validate_schema(connection)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"Falha de integridade do snapshot SQLite: {integrity}")
        run_count = int(connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0])

        for reference_path in references:
            if not reference_path.is_file():
                raise FileNotFoundError(f"Referência de run não encontrada: {reference_path}")
            reference = json.loads(reference_path.read_text(encoding="utf-8"))
            run_id = str(reference["run_id"])
            expected_experiment_id = str(reference["experiment_id"])
            row = connection.execute(
                "SELECT experiment_id, status, artifact_uri FROM runs WHERE run_uuid = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Run {run_id} de {reference_path} não existe no snapshot.")

            experiment_id, status, artifact_uri = map(str, row)
            if experiment_id != expected_experiment_id:
                raise RuntimeError(
                    f"Run {run_id} pertence ao experimento {experiment_id}, "
                    f"não ao {expected_experiment_id}."
                )
            if status != "FINISHED":
                raise RuntimeError(f"Run referenciado {run_id} possui status {status!r}.")
            for table in ("params", "metrics"):
                record_count = int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE run_uuid = ?",  # noqa: S608
                        (run_id,),
                    ).fetchone()[0]
                )
                if record_count == 0:
                    raise RuntimeError(f"Run referenciado {run_id} não possui {table}.")
            expected_suffix = f"/{experiment_id}/{run_id}/artifacts"
            if not artifact_uri.replace("\\", "/").rstrip("/").endswith(expected_suffix):
                raise RuntimeError(
                    f"URI de artefatos inesperada para o run {run_id}: {artifact_uri}"
                )

            run_artifacts = artifacts_root / experiment_id / run_id / "artifacts"
            contains_files = run_artifacts.is_dir() and any(
                path.is_file() for path in run_artifacts.rglob("*")
            )
            if not contains_files:
                raise RuntimeError(f"Artefatos do run referenciado {run_id} estão ausentes.")

    return SnapshotSummary(run_count, artifact_file_count, len(references))


def publish_snapshot(
    source_database: Path,
    source_artifacts: Path,
    destination_database: Path,
    destination_artifacts: Path,
    canonical_artifacts_root: Path,
    references: tuple[Path, ...],
) -> SnapshotSummary:
    """Copia artefatos primeiro e publica o banco somente sem runs ativos."""
    active_runs = _active_runs(source_database)
    if active_runs:
        joined = ", ".join(active_runs)
        raise RuntimeError(f"Snapshot recusado: existem runs ativos no MLflow: {joined}")

    _copy_artifacts(source_artifacts, destination_artifacts)
    _backup_database(source_database, destination_database, canonical_artifacts_root)

    active_runs_after_copy = _active_runs(source_database)
    if active_runs_after_copy:
        joined = ", ".join(active_runs_after_copy)
        raise RuntimeError(f"Snapshot inválido: um run iniciou durante a cópia: {joined}")

    return validate_snapshot(destination_database, destination_artifacts, references)


def main() -> int:
    args = parse_args()
    destination_database = _resolved(args.destination_database)
    destination_artifacts = _resolved(args.destination_artifacts)
    references = tuple(
        _resolved(path) for path in (args.references or list(DEFAULT_REFERENCES))
    )

    if args.check_only:
        summary = validate_snapshot(destination_database, destination_artifacts, references)
        action = "validado"
    else:
        summary = publish_snapshot(
            _resolved(args.source_database),
            _resolved(args.source_artifacts),
            destination_database,
            destination_artifacts,
            args.canonical_artifacts_root.resolve(),
            references,
        )
        action = "publicado"

    print(
        f"Snapshot MLflow {action}: {summary.run_count} runs, "
        f"{summary.artifact_file_count} arquivos e "
        f"{summary.reference_count} referências válidas."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
