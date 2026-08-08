"""Resolve o backend de tracking do MLflow para host local ou Compose."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_tracking_uri(database_path: Path) -> str:
    """Prioriza o servidor configurado e preserva SQLite como fallback local."""
    configured_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()
    if configured_uri:
        return configured_uri

    database_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{database_path.resolve().as_posix()}"
