"""Teste ponta a ponta dos baselines do M3."""

from __future__ import annotations

import json

import joblib
import pandas as pd

from src.models.train_propensity import (
    PROPENSITY_INPUT_COLUMNS,
    load_modeling_config,
    load_processed_splits,
    run_m3_training,
)


def test_m3_training_beats_dummy_and_reuses_fitted_pipeline() -> None:
    """Treina sem tracking, valida gate e executa inferência com o artefato salvo."""
    report = run_m3_training("configs/modeling.yaml", enable_tracking=False)
    config = load_modeling_config("configs/modeling.yaml")
    splits, _ = load_processed_splits(config)

    assert report["selection"]["gate_passed"] is True
    assert report["selection"]["selected_model"] == "logistic_propensity"
    logistic_validation = report["predictive_models"]["logistic_regression"]["validation"]
    dummy_validation = report["predictive_models"]["dummy"]["validation"]
    assert logistic_validation["average_precision"] > dummy_validation["average_precision"]
    assert logistic_validation["brier_score"] < dummy_validation["brier_score"]
    assert report["fixed_policy"]["best_action"] == "celular"

    artifact = joblib.load(config.model_path)
    assert artifact["fit_split"] == "train"
    assert artifact["selection_split"] == "validation"
    assert artifact["input_columns"] == PROPENSITY_INPUT_COLUMNS
    assert "duracao_contato" not in artifact["input_columns"]
    assert "contatos_campanha_atual" not in artifact["input_columns"]

    test_payload = splits["test"].loc[:, PROPENSITY_INPUT_COLUMNS].iloc[[0]]
    probability = artifact["pipeline"].predict_proba(test_payload)[0, 1]
    assert 0 <= probability <= 1

    saved_report = json.loads(config.metrics_path.read_text(encoding="utf-8"))
    assert saved_report == report
    predictions = pd.read_csv(config.test_predictions_path)
    assert len(predictions) == len(splits["test"])
    assert predictions["propensity_probability"].between(0, 1).all()
    slice_metrics = pd.read_csv(config.test_slice_metrics_path)
    assert not slice_metrics.empty
    assert slice_metrics["row_count"].ge(config.minimum_slice_size).all()
    assert report["audit_slices"]["evaluated_slice_count"] == len(slice_metrics)
