"""Testes das métricas e do limiar do baseline preditivo."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.models.train_propensity import evaluate_probabilities, select_f1_threshold


def test_f1_threshold_is_selected_from_validation_predictions() -> None:
    """Seleciona um limiar observado sem acessar dados de teste."""
    y_true = pd.Series([0, 0, 1, 1])
    probabilities = np.array([0.1, 0.4, 0.6, 0.9])
    selection = select_f1_threshold(y_true, probabilities)

    assert 0 < selection["threshold"] < 1
    assert selection["validation_f1"] == 1.0


def test_probability_metrics_include_calibration_and_confusion_matrix() -> None:
    """Garante cobertura das evidências exigidas pelo M3."""
    y_true = pd.Series([0, 0, 1, 1])
    probabilities = np.array([0.1, 0.2, 0.7, 0.8])
    metrics = evaluate_probabilities(y_true, probabilities, threshold=0.5)

    assert metrics["average_precision"] == 1.0
    assert metrics["roc_auc"] == 1.0
    assert metrics["brier_score"] > 0
    assert metrics["f1"] == 1.0
    assert metrics["confusion_matrix"]["true_positives"] == 2
    assert metrics["calibration_curve"]
