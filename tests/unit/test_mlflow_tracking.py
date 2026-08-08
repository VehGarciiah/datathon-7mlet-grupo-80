"""Testes da seleção do backend de tracking do MLflow."""

from pathlib import Path

from src.observability.mlflow_tracking import resolve_tracking_uri


def test_tracking_uri_uses_local_sqlite_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)

    database_path = tmp_path / "tracking" / "mlflow.db"

    assert resolve_tracking_uri(database_path) == (
        f"sqlite:///{database_path.resolve().as_posix()}"
    )
    assert database_path.parent.is_dir()


def test_tracking_uri_prefers_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "  http://mlflow:5000  ")

    assert resolve_tracking_uri(tmp_path / "mlflow.db") == "http://mlflow:5000"
