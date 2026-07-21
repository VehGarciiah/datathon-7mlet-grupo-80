"""Testes do preprocessing ajustado exclusivamente no treino."""

from __future__ import annotations

import numpy as np

from src.data.prepare import (
    fit_and_transform_splits,
    load_preparation_config,
    load_validated_interim,
    split_model_table,
)
from src.features.build_features import CONTEXT_COLUMNS, build_feature_tables


def test_preprocessor_is_fitted_only_with_training_rows() -> None:
    """Usa o contador do scaler como evidência do conjunto usado no fit."""
    config = load_preparation_config("configs/data.yaml")
    interim_frame = load_validated_interim(config)
    feature_result = build_feature_tables(interim_frame)
    splits = split_model_table(feature_result.model_table, config)

    preprocessor, matrices, feature_names = fit_and_transform_splits(splits)
    numeric_pipeline = preprocessor.named_transformers_["numeric"]
    scaler = numeric_pipeline.named_steps["scaler"]

    assert list(preprocessor.feature_names_in_) == CONTEXT_COLUMNS
    assert np.all(np.asarray(scaler.n_samples_seen_) == len(splits["train"]))
    assert matrices["train"].shape[0] == len(splits["train"])
    assert matrices["validation"].shape[0] == len(splits["validation"])
    assert matrices["test"].shape[0] == len(splits["test"])
    assert all(matrix.shape[1] == len(feature_names) for matrix in matrices.values())
