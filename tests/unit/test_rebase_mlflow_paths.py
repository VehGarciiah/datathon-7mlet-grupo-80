"""Testes da adaptação portátil das URIs do MLflow."""

from __future__ import annotations

import sqlite3

from scripts.rebase_mlflow_paths import (
    collect_mismatches,
    expected_experiment_uri,
    expected_run_uri,
)


def test_deleted_run_does_not_require_an_artifact_directory(tmp_path) -> None:
    artifacts_root = tmp_path / "mlruns"
    active_artifacts = artifacts_root / "1" / "active-run" / "artifacts"
    active_artifacts.mkdir(parents=True)

    with sqlite3.connect(":memory:") as connection:
        connection.execute(
            "CREATE TABLE experiments (experiment_id INTEGER, artifact_location TEXT)"
        )
        connection.execute(
            """
            CREATE TABLE runs (
                run_uuid TEXT,
                experiment_id INTEGER,
                artifact_uri TEXT,
                lifecycle_stage TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO experiments VALUES (?, ?)",
            (1, expected_experiment_uri(artifacts_root, "1")),
        )
        connection.executemany(
            "INSERT INTO runs VALUES (?, ?, ?, ?)",
            (
                (
                    "active-run",
                    1,
                    expected_run_uri(artifacts_root, "1", "active-run"),
                    "active",
                ),
                (
                    "deleted-run",
                    1,
                    expected_run_uri(artifacts_root, "1", "deleted-run"),
                    "deleted",
                ),
            ),
        )

        assert collect_mismatches(connection, artifacts_root) == []

        active_artifacts.rmdir()
        mismatches = collect_mismatches(connection, artifacts_root)

    assert len(mismatches) == 1
    assert "active-run" in mismatches[0]
