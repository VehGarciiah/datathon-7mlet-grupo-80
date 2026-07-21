"""Testes de integração da camada canônica persistida."""

from __future__ import annotations

import json

import pandas as pd

from src.data.translate import compute_sha256, load_pipeline_config
from src.data.validate import validate_translated_dataset


def test_interim_artifact_and_metadata_are_consistent() -> None:
    """Compara o CSV gerado com sua evidência de linhagem."""
    config = load_pipeline_config("configs/data.yaml")
    assert config.interim_path.exists()
    assert config.metadata_path.exists()

    frame = pd.read_csv(
        config.interim_path,
        sep=config.interim_delimiter,
        encoding=config.interim_encoding,
    )
    report = validate_translated_dataset(frame)
    metadata = json.loads(config.metadata_path.read_text(encoding="utf-8"))

    assert metadata["interim"]["sha256"] == compute_sha256(config.interim_path)
    assert metadata["interim"]["validation"] == report.to_dict()
    assert metadata["translation"]["mapped_source_columns"] == 21
    assert metadata["translation"]["business_rows_removed"] == 0
