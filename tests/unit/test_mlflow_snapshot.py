"""Testes do snapshot publicável do MLflow containerizado."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.snapshot_mlflow import publish_snapshot, validate_snapshot


def _create_database(path: Path, *, status: str = "FINISHED") -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE experiments (experiment_id INTEGER, artifact_location TEXT)"
        )
        connection.execute(
            """
            CREATE TABLE runs (
                run_uuid TEXT,
                experiment_id INTEGER,
                artifact_uri TEXT,
                status TEXT
            )
            """
        )
        connection.execute("INSERT INTO experiments VALUES (1, 'file:///origem/1')")
        connection.execute(
            "INSERT INTO runs VALUES ('final-run', 1, 'file:///origem/1/final-run/artifacts', ?)",
            (status,),
        )
        connection.execute("CREATE TABLE params (run_uuid TEXT, key TEXT, value TEXT)")
        connection.execute("CREATE TABLE metrics (run_uuid TEXT, key TEXT, value REAL)")
        connection.execute("INSERT INTO params VALUES ('final-run', 'seed', '42')")
        connection.execute("INSERT INTO metrics VALUES ('final-run', 'reward', 0.2)")


def _create_reference(path: Path, run_id: str = "final-run") -> None:
    path.write_text(
        json.dumps({"experiment_id": 1, "run_id": run_id}),
        encoding="utf-8",
    )


def test_publish_snapshot_copies_database_artifacts_and_validates_reference(tmp_path) -> None:
    source_database = tmp_path / "source.db"
    source_artifacts = tmp_path / "source-runs"
    artifact = source_artifacts / "1" / "final-run" / "artifacts" / "metrics.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}", encoding="utf-8")
    _create_database(source_database)
    reference = tmp_path / "latest.json"
    _create_reference(reference)

    destination_database = tmp_path / "snapshot.db"
    destination_artifacts = tmp_path / "snapshot-runs"
    canonical_root = tmp_path / "canonical-mlruns"
    summary = publish_snapshot(
        source_database,
        source_artifacts,
        destination_database,
        destination_artifacts,
        canonical_root,
        (reference,),
    )

    assert summary.run_count == 1
    assert summary.artifact_file_count == 1
    assert summary.reference_count == 1
    assert (destination_artifacts / "1/final-run/artifacts/metrics.json").is_file()
    with sqlite3.connect(destination_database) as connection:
        artifact_uri = connection.execute(
            "SELECT artifact_uri FROM runs WHERE run_uuid = 'final-run'"
        ).fetchone()[0]
    assert artifact_uri == f"{canonical_root.as_uri()}/1/final-run/artifacts"


def test_validate_snapshot_rejects_reference_missing_from_database(tmp_path) -> None:
    database = tmp_path / "snapshot.db"
    artifacts = tmp_path / "mlruns"
    artifacts.mkdir()
    _create_database(database)
    reference = tmp_path / "latest.json"
    _create_reference(reference, run_id="missing-run")

    with pytest.raises(RuntimeError, match="não existe no snapshot"):
        validate_snapshot(database, artifacts, (reference,))


def test_publish_snapshot_refuses_active_runs(tmp_path) -> None:
    source_database = tmp_path / "source.db"
    source_artifacts = tmp_path / "source-runs"
    source_artifacts.mkdir()
    _create_database(source_database, status="RUNNING")

    with pytest.raises(RuntimeError, match="existem runs ativos"):
        publish_snapshot(
            source_database,
            source_artifacts,
            tmp_path / "snapshot.db",
            tmp_path / "snapshot-runs",
            Path("/mlflow/mlruns"),
            (),
        )
