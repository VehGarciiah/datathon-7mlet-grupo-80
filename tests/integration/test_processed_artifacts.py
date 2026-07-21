"""Teste de integração dos artefatos produzidos no M2."""

from __future__ import annotations

import json

import joblib
import pandas as pd
from scipy import sparse

from src.data.prepare import build_processed_datasets, load_preparation_config
from src.data.translate import compute_sha256
from src.features.build_features import (
    AUDIT_ONLY_COLUMNS,
    BLOCKED_MODEL_COLUMNS,
    CONTEXT_COLUMNS,
    IDENTIFIER_COLUMN,
)


def test_m2_artifacts_are_consistent_and_reproducible() -> None:
    """Executa o pipeline e cruza CSVs, matrizes, contrato e hashes."""
    metadata = build_processed_datasets("configs/data.yaml")
    config = load_preparation_config("configs/data.yaml")

    split_paths = {
        "train": config.train_path,
        "validation": config.validation_path,
        "test": config.test_path,
    }
    frames = {
        name: pd.read_csv(path, sep=config.csv_delimiter, encoding=config.csv_encoding)
        for name, path in split_paths.items()
    }
    all_ids = set()
    for name, frame in frames.items():
        current_ids = set(frame[IDENTIFIER_COLUMN])
        assert all_ids.isdisjoint(current_ids)
        all_ids.update(current_ids)
        assert not BLOCKED_MODEL_COLUMNS.intersection(CONTEXT_COLUMNS)
        assert "duracao_contato" not in frame.columns
        assert metadata["outputs"][name]["sha256"] == compute_sha256(split_paths[name])

    assert len(all_ids) == config.expected_rows_after_deduplication
    audit_frame = pd.read_csv(
        config.audit_path,
        sep=config.csv_delimiter,
        encoding=config.csv_encoding,
    )
    assert set(AUDIT_ONLY_COLUMNS).issubset(audit_frame.columns)
    assert set(CONTEXT_COLUMNS).isdisjoint(audit_frame.columns)

    artifact = joblib.load(config.preprocessor_path)
    assert artifact["fit_split"] == "train"
    assert artifact["context_columns"] == CONTEXT_COLUMNS
    assert artifact["feature_names"] == metadata["preprocessing"]["feature_names"]

    matrix_paths = {
        "train": config.train_matrix_path,
        "validation": config.validation_matrix_path,
        "test": config.test_matrix_path,
    }
    for name, path in matrix_paths.items():
        matrix = sparse.load_npz(path)
        assert list(matrix.shape) == metadata["preprocessing"]["matrix_shapes"][name]

    saved_metadata = json.loads(config.metadata_path.read_text(encoding="utf-8"))
    assert saved_metadata == metadata
    assert metadata["deduplication"]["business_rows_removed"] == 12
