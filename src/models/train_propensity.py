"""Treina e avalia os baselines do M3 com rastreabilidade local."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import mlflow
import numpy as np
import pandas as pd
import scipy
import sklearn
import yaml
from sklearn.calibration import calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.data.contracts import DataContractError
from src.data.prepare import load_preparation_config
from src.data.translate import compute_sha256
from src.features.build_features import (
    ACTION_COLUMN,
    AUDIT_ONLY_COLUMNS,
    BINARY_CONTEXT_COLUMNS,
    CATEGORICAL_CONTEXT_COLUMNS,
    CONTEXT_COLUMNS,
    IDENTIFIER_COLUMN,
    NUMERIC_CONTEXT_COLUMNS,
    TARGET_COLUMN,
)
from src.observability.mlflow_tracking import resolve_tracking_uri
from src.policies.fixed import BestHistoricalActionPolicy, evaluate_logged_replay

PROPENSITY_INPUT_COLUMNS = [*CONTEXT_COLUMNS, ACTION_COLUMN]
PROPENSITY_CATEGORICAL_COLUMNS = [*CATEGORICAL_CONTEXT_COLUMNS, ACTION_COLUMN]


@dataclass(frozen=True)
class ModelingConfig:
    """Reúne parâmetros e caminhos usados no M3."""

    project_root: Path
    data_config_path: Path
    experiment_config_path: Path
    action_order: list[str]
    policy_id: str
    policy_version: str
    fixed_confidence_level: float
    fixed_policy_path: Path
    dummy_strategy: str
    dummy_threshold: float
    model_id: str
    model_version: str
    logistic_c: float
    logistic_max_iter: int
    logistic_solver: str
    logistic_class_weight: str | None
    random_seed: int
    model_path: Path
    metrics_path: Path
    fixed_baseline_path: Path
    coefficients_path: Path
    validation_predictions_path: Path
    test_predictions_path: Path
    test_slice_metrics_path: Path
    latest_mlflow_run_path: Path
    minimum_slice_size: int
    audit_slice_columns: list[str]
    tracking_enabled: bool
    tracking_database_path: Path
    experiment_name: str
    run_name: str


def _read_yaml(path: Path) -> dict[str, Any]:
    """Carrega uma configuração YAML e rejeita conteúdo vazio."""
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise DataContractError(f"Configuração inválida ou vazia: {path}.")
    return content


def load_modeling_config(config_path: str | Path = "configs/modeling.yaml") -> ModelingConfig:
    """Resolve configuração, ações canônicas e caminhos do M3."""
    resolved_path = Path(config_path).resolve()
    project_root = resolved_path.parent.parent
    config = _read_yaml(resolved_path)
    experiment_path = project_root / config["experiment_config_path"]
    experiment = _read_yaml(experiment_path)
    action_order = [item["canonical_value_ptbr"] for item in experiment["decision"]["actions"]]
    fixed = config["fixed_policy"]
    model = config["propensity_model"]
    logistic = model["logistic_regression"]
    evaluation = config["evaluation"]
    reports = config["reports"]
    tracking = config["tracking"]
    return ModelingConfig(
        project_root=project_root,
        data_config_path=project_root / config["data_config_path"],
        experiment_config_path=experiment_path,
        action_order=action_order,
        policy_id=fixed["id"],
        policy_version=fixed["version"],
        fixed_confidence_level=float(fixed["confidence_level"]),
        fixed_policy_path=project_root / fixed["artifact_path"],
        dummy_strategy=model["dummy"]["strategy"],
        dummy_threshold=float(model["dummy"]["threshold"]),
        model_id=model["id"],
        model_version=model["version"],
        logistic_c=float(logistic["C"]),
        logistic_max_iter=int(logistic["max_iter"]),
        logistic_solver=logistic["solver"],
        logistic_class_weight=logistic["class_weight"],
        random_seed=int(logistic["random_seed"]),
        model_path=project_root / model["artifact_path"],
        metrics_path=project_root / reports["metrics_path"],
        fixed_baseline_path=project_root / reports["fixed_baseline_path"],
        coefficients_path=project_root / reports["coefficients_path"],
        validation_predictions_path=project_root / reports["validation_predictions_path"],
        test_predictions_path=project_root / reports["test_predictions_path"],
        test_slice_metrics_path=project_root / reports["test_slice_metrics_path"],
        latest_mlflow_run_path=project_root / reports["latest_mlflow_run_path"],
        minimum_slice_size=int(evaluation["minimum_slice_size"]),
        audit_slice_columns=list(evaluation["audit_slice_columns"]),
        tracking_enabled=bool(tracking["enabled"]),
        tracking_database_path=project_root / tracking["database_path"],
        experiment_name=tracking["experiment_name"],
        run_name=tracking["run_name"],
    )


def load_processed_splits(config: ModelingConfig) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    """Confere hashes do M2 antes de abrir treino, validação e teste."""
    preparation_config = load_preparation_config(config.data_config_path)
    metadata = json.loads(preparation_config.metadata_path.read_text(encoding="utf-8"))
    paths = {
        "train": preparation_config.train_path,
        "validation": preparation_config.validation_path,
        "test": preparation_config.test_path,
    }
    frames: dict[str, pd.DataFrame] = {}
    expected_columns = [IDENTIFIER_COLUMN, *CONTEXT_COLUMNS, ACTION_COLUMN, TARGET_COLUMN]
    for name, path in paths.items():
        actual_hash = compute_sha256(path)
        expected_hash = metadata["outputs"][name]["sha256"]
        if actual_hash != expected_hash:
            raise DataContractError(
                f"Hash do split '{name}' divergente: esperado={expected_hash}; "
                f"recebido={actual_hash}."
            )
        frame = pd.read_csv(
            path,
            sep=preparation_config.csv_delimiter,
            encoding=preparation_config.csv_encoding,
        )
        if list(frame.columns) != expected_columns:
            raise DataContractError(f"Contrato de colunas divergente no split '{name}'.")
        frames[name] = frame
    return frames, metadata


def create_propensity_pipeline(config: ModelingConfig) -> Pipeline:
    """Cria Regressão Logística com preprocessing interno e treinável em conjunto."""
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "encoder",
                OneHotEncoder(handle_unknown="ignore", sparse_output=True, dtype=np.float64),
            ),
        ]
    )
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("categorical", categorical_pipeline, PROPENSITY_CATEGORICAL_COLUMNS),
            ("numeric", numeric_pipeline, NUMERIC_CONTEXT_COLUMNS),
            ("binary", "passthrough", BINARY_CONTEXT_COLUMNS),
        ],
        remainder="drop",
        sparse_threshold=1.0,
        verbose_feature_names_out=False,
    )
    classifier = LogisticRegression(
        C=config.logistic_c,
        max_iter=config.logistic_max_iter,
        solver=config.logistic_solver,
        class_weight=config.logistic_class_weight,
        random_state=config.random_seed,
    )
    return Pipeline(steps=[("preprocessor", preprocessor), ("classifier", classifier)])


def select_f1_threshold(y_true: pd.Series, probabilities: np.ndarray) -> dict[str, float]:
    """Seleciona o limiar na validação e resolve empates pelo menor valor."""
    precision, recall, thresholds = precision_recall_curve(y_true, probabilities)
    if len(thresholds) == 0:
        return {"threshold": 0.5, "validation_f1": 0.0}
    denominator = precision[:-1] + recall[:-1]
    f1_values = np.divide(
        2 * precision[:-1] * recall[:-1],
        denominator,
        out=np.zeros_like(denominator),
        where=denominator > 0,
    )
    best_index = int(np.flatnonzero(f1_values == f1_values.max())[0])
    return {
        "threshold": float(thresholds[best_index]),
        "validation_f1": float(f1_values[best_index]),
    }


def evaluate_probabilities(
    y_true: pd.Series,
    probabilities: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    """Calcula discriminação, calibração e métricas de classificação."""
    predictions = (probabilities >= threshold).astype(int)
    true_negatives, false_positives, false_negatives, true_positives = confusion_matrix(
        y_true,
        predictions,
        labels=[0, 1],
    ).ravel()
    fraction_positive, mean_predicted = calibration_curve(
        y_true,
        probabilities,
        n_bins=10,
        strategy="quantile",
    )
    return {
        "threshold": float(threshold),
        "row_count": len(y_true),
        "positive_rate": float(y_true.mean()),
        "predicted_positive_rate": float(predictions.mean()),
        "average_precision": float(average_precision_score(y_true, probabilities)),
        "roc_auc": float(roc_auc_score(y_true, probabilities)),
        "brier_score": float(brier_score_loss(y_true, probabilities)),
        "log_loss": float(log_loss(y_true, probabilities, labels=[0, 1])),
        "accuracy": float(accuracy_score(y_true, predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, predictions)),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "recall": float(recall_score(y_true, predictions, zero_division=0)),
        "f1": float(f1_score(y_true, predictions, zero_division=0)),
        "confusion_matrix": {
            "true_negatives": int(true_negatives),
            "false_positives": int(false_positives),
            "false_negatives": int(false_negatives),
            "true_positives": int(true_positives),
        },
        "calibration_curve": [
            {"mean_predicted_probability": float(predicted), "observed_fraction": float(observed)}
            for predicted, observed in zip(mean_predicted, fraction_positive, strict=True)
        ],
    }


def _write_json(content: dict[str, Any], path: Path) -> None:
    """Grava JSON ordenado para facilitar revisão e diff."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary_path.replace(path)


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    """Grava CSV de relatório com separador interoperável."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary_path, index=False, lineterminator="\n")
    temporary_path.replace(path)


def _write_joblib(content: dict[str, Any], path: Path) -> None:
    """Serializa artefato de forma atômica."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    joblib.dump(content, temporary_path)
    temporary_path.replace(path)


def _build_predictions(
    frame: pd.DataFrame,
    dummy_probabilities: np.ndarray,
    propensity_probabilities: np.ndarray,
    threshold: float,
    split_name: str,
) -> pd.DataFrame:
    """Cria evidência por evento sem incluir atributos de contexto."""
    return pd.DataFrame(
        {
            IDENTIFIER_COLUMN: frame[IDENTIFIER_COLUMN].to_numpy(),
            "split": split_name,
            "logged_action": frame[ACTION_COLUMN].to_numpy(),
            TARGET_COLUMN: frame[TARGET_COLUMN].to_numpy(),
            "dummy_probability": dummy_probabilities,
            "propensity_probability": propensity_probabilities,
            "propensity_prediction": (propensity_probabilities >= threshold).astype(int),
        }
    )


def evaluate_audit_slices(
    predictions: pd.DataFrame,
    audit_frame: pd.DataFrame,
    *,
    threshold: float,
    minimum_slice_size: int,
    slice_columns: list[str],
) -> pd.DataFrame:
    """Avalia o teste por fatias sem usar os campos de auditoria como features."""
    expected_audit_columns = {IDENTIFIER_COLUMN, "split", *AUDIT_ONLY_COLUMNS}
    missing = sorted(expected_audit_columns - set(audit_frame.columns))
    if missing:
        raise DataContractError(f"Colunas ausentes na camada de auditoria: {missing}.")

    test_audit = audit_frame.loc[audit_frame["split"].eq("test")].copy()
    test_audit["faixa_idade"] = pd.cut(
        test_audit["idade"],
        bins=[float("-inf"), 29, 39, 49, 59, float("inf")],
        labels=["ate_29", "30_39", "40_49", "50_59", "60_mais"],
    ).astype("string")
    merged = predictions.merge(
        test_audit,
        on=IDENTIFIER_COLUMN,
        how="inner",
        validate="one_to_one",
    )
    if len(merged) != len(predictions):
        raise DataContractError("A camada de auditoria não cobre todas as predições de teste.")

    rows: list[dict[str, Any]] = []
    for column in slice_columns:
        if column not in merged.columns:
            raise DataContractError(f"Fatia de auditoria desconhecida: {column}.")
        for value, group in merged.groupby(column, dropna=False, observed=True):
            if len(group) < minimum_slice_size or group[TARGET_COLUMN].nunique() < 2:
                continue
            metrics = evaluate_probabilities(
                group[TARGET_COLUMN],
                group["propensity_probability"].to_numpy(),
                threshold,
            )
            rows.append(
                {
                    "slice_column": column,
                    "slice_value": "ausente" if pd.isna(value) else str(value),
                    "row_count": metrics["row_count"],
                    "positive_rate": metrics["positive_rate"],
                    "average_precision": metrics["average_precision"],
                    "roc_auc": metrics["roc_auc"],
                    "brier_score": metrics["brier_score"],
                    "precision": metrics["precision"],
                    "recall": metrics["recall"],
                    "f1": metrics["f1"],
                }
            )
    result_columns = [
        "slice_column",
        "slice_value",
        "row_count",
        "positive_rate",
        "average_precision",
        "roc_auc",
        "brier_score",
        "precision",
        "recall",
        "f1",
    ]
    if not rows:
        return pd.DataFrame(columns=result_columns)
    return (
        pd.DataFrame(rows, columns=result_columns)
        .sort_values(
            ["slice_column", "average_precision"],
            ascending=[True, False],
        )
        .reset_index(drop=True)
    )


def _log_mlflow_run(
    config: ModelingConfig,
    report: dict[str, Any],
    artifact_paths: list[Path],
) -> dict[str, str]:
    """Registra parâmetros, métricas e artefatos no backend configurado."""
    mlflow.set_tracking_uri(resolve_tracking_uri(config.tracking_database_path))
    mlflow.set_experiment(config.experiment_name)
    with mlflow.start_run(run_name=config.run_name) as run:
        mlflow.set_tags(
            {
                "milestone": "M3",
                "model_id": config.model_id,
                "policy_id": config.policy_id,
                "causal_claim": "false",
            }
        )
        mlflow.log_params(
            {
                "fit_split": "train",
                "selection_split": "validation",
                "selection_metric": "average_precision",
                "threshold_strategy": "max_f1_on_validation",
                "logistic_C": config.logistic_c,
                "logistic_solver": config.logistic_solver,
                "logistic_max_iter": config.logistic_max_iter,
                "random_seed": config.random_seed,
                "input_feature_count": len(PROPENSITY_INPUT_COLUMNS),
                "best_fixed_action": report["fixed_policy"]["best_action"],
                "fixed_confidence_level": config.fixed_confidence_level,
            }
        )
        mlflow.log_metrics(
            {
                "validation_dummy_average_precision": report["predictive_models"]["dummy"][
                    "validation"
                ]["average_precision"],
                "validation_logistic_average_precision": report["predictive_models"][
                    "logistic_regression"
                ]["validation"]["average_precision"],
                "validation_logistic_brier": report["predictive_models"]["logistic_regression"][
                    "validation"
                ]["brier_score"],
                "test_logistic_average_precision": report["predictive_models"][
                    "logistic_regression"
                ]["test"]["average_precision"],
                "test_logistic_roc_auc": report["predictive_models"]["logistic_regression"]["test"][
                    "roc_auc"
                ],
                "test_logistic_brier": report["predictive_models"]["logistic_regression"]["test"][
                    "brier_score"
                ],
                "test_fixed_mean_reward": report["fixed_policy"]["replay"]["test"]["mean_reward"],
                "test_fixed_replay_coverage": report["fixed_policy"]["replay"]["test"][
                    "replay_coverage"
                ],
            }
        )
        for path in artifact_paths:
            mlflow.log_artifact(str(path))
        return {
            "run_id": run.info.run_id,
            "experiment_id": run.info.experiment_id,
            "tracking_uri": mlflow.get_tracking_uri(),
            "run_name": config.run_name,
        }


def run_m3_training(
    config_path: str | Path = "configs/modeling.yaml",
    *,
    enable_tracking: bool | None = None,
) -> dict[str, Any]:
    """Treina baselines, avalia splits e persiste todas as evidências do M3."""
    config = load_modeling_config(config_path)
    splits, preparation_metadata = load_processed_splits(config)
    train_frame = splits["train"]
    validation_frame = splits["validation"]
    test_frame = splits["test"]

    fixed_policy = BestHistoricalActionPolicy(
        config.action_order,
        policy_id=config.policy_id,
        version=config.policy_version,
        confidence_level=config.fixed_confidence_level,
    ).fit(train_frame)
    fixed_report = {
        **fixed_policy.to_dict(),
        "replay": {
            "validation": evaluate_logged_replay(fixed_policy, validation_frame),
            "test": evaluate_logged_replay(fixed_policy, test_frame),
        },
    }
    _write_json(fixed_report, config.fixed_baseline_path)
    _write_joblib({"schema_version": "1.0.0", "policy": fixed_policy}, config.fixed_policy_path)

    train_x = train_frame.loc[:, PROPENSITY_INPUT_COLUMNS]
    train_y = train_frame[TARGET_COLUMN]
    validation_x = validation_frame.loc[:, PROPENSITY_INPUT_COLUMNS]
    validation_y = validation_frame[TARGET_COLUMN]
    test_x = test_frame.loc[:, PROPENSITY_INPUT_COLUMNS]
    test_y = test_frame[TARGET_COLUMN]

    dummy_model = DummyClassifier(strategy=config.dummy_strategy, random_state=config.random_seed)
    dummy_model.fit(train_x, train_y)
    logistic_pipeline = create_propensity_pipeline(config)
    logistic_pipeline.fit(train_x, train_y)

    probabilities = {
        "dummy_validation": dummy_model.predict_proba(validation_x)[:, 1],
        "dummy_test": dummy_model.predict_proba(test_x)[:, 1],
        "logistic_train": logistic_pipeline.predict_proba(train_x)[:, 1],
        "logistic_validation": logistic_pipeline.predict_proba(validation_x)[:, 1],
        "logistic_test": logistic_pipeline.predict_proba(test_x)[:, 1],
    }
    threshold_selection = select_f1_threshold(validation_y, probabilities["logistic_validation"])
    selected_threshold = threshold_selection["threshold"]

    predictive_report = {
        "dummy": {
            "strategy": config.dummy_strategy,
            "fit_split": "train",
            "validation": evaluate_probabilities(
                validation_y,
                probabilities["dummy_validation"],
                config.dummy_threshold,
            ),
            "test": evaluate_probabilities(
                test_y,
                probabilities["dummy_test"],
                config.dummy_threshold,
            ),
        },
        "logistic_regression": {
            "model_id": config.model_id,
            "model_version": config.model_version,
            "fit_split": "train",
            "threshold_selection_split": "validation",
            "threshold_selection": threshold_selection,
            "train": evaluate_probabilities(
                train_y,
                probabilities["logistic_train"],
                selected_threshold,
            ),
            "validation": evaluate_probabilities(
                validation_y,
                probabilities["logistic_validation"],
                selected_threshold,
            ),
            "test": evaluate_probabilities(
                test_y,
                probabilities["logistic_test"],
                selected_threshold,
            ),
        },
    }
    validation_gain = (
        predictive_report["logistic_regression"]["validation"]["average_precision"]
        - predictive_report["dummy"]["validation"]["average_precision"]
    )

    fitted_preprocessor = logistic_pipeline.named_steps["preprocessor"]
    classifier = logistic_pipeline.named_steps["classifier"]
    transformed_feature_names = fitted_preprocessor.get_feature_names_out().tolist()
    coefficients = pd.DataFrame(
        {
            "feature": transformed_feature_names,
            "coefficient": classifier.coef_[0],
            "odds_ratio": np.exp(classifier.coef_[0]),
        }
    ).sort_values("coefficient", ascending=False)
    _write_csv(coefficients, config.coefficients_path)

    validation_predictions = _build_predictions(
        validation_frame,
        probabilities["dummy_validation"],
        probabilities["logistic_validation"],
        selected_threshold,
        "validation",
    )
    test_predictions = _build_predictions(
        test_frame,
        probabilities["dummy_test"],
        probabilities["logistic_test"],
        selected_threshold,
        "test",
    )
    _write_csv(validation_predictions, config.validation_predictions_path)
    _write_csv(test_predictions, config.test_predictions_path)

    preparation_config = load_preparation_config(config.data_config_path)
    audit_frame = pd.read_csv(
        preparation_config.audit_path,
        sep=preparation_config.csv_delimiter,
        encoding=preparation_config.csv_encoding,
    )
    slice_metrics = evaluate_audit_slices(
        test_predictions,
        audit_frame,
        threshold=selected_threshold,
        minimum_slice_size=config.minimum_slice_size,
        slice_columns=config.audit_slice_columns,
    )
    _write_csv(slice_metrics, config.test_slice_metrics_path)

    model_artifact = {
        "schema_version": "1.0.0",
        "model_id": config.model_id,
        "model_version": config.model_version,
        "fit_split": "train",
        "selection_split": "validation",
        "input_columns": PROPENSITY_INPUT_COLUMNS,
        "transformed_feature_names": transformed_feature_names,
        "threshold": selected_threshold,
        "pipeline": logistic_pipeline,
    }
    _write_joblib(model_artifact, config.model_path)
    smoke_probability = float(logistic_pipeline.predict_proba(test_x.iloc[[0]])[0, 1])

    report = {
        "schema_version": "1.0.0",
        "milestone": "M3",
        "data": {
            "preparation_metadata_sha256": compute_sha256(preparation_config.metadata_path),
            "split_hashes": {
                name: preparation_metadata["outputs"][name]["sha256"]
                for name in ["train", "validation", "test"]
            },
        },
        "contracts": {
            "input_columns": PROPENSITY_INPUT_COLUMNS,
            "transformed_feature_count": len(transformed_feature_names),
            "action_column": ACTION_COLUMN,
            "target_column": TARGET_COLUMN,
            "blocked_columns_absent": [
                "duracao_contato",
                "contatos_campanha_atual",
                IDENTIFIER_COLUMN,
            ],
        },
        "fixed_policy": fixed_report,
        "predictive_models": predictive_report,
        "selection": {
            "primary_metric": "average_precision",
            "validation_gain_over_dummy": validation_gain,
            "gate_passed": validation_gain > 0,
            "selected_model": config.model_id if validation_gain > 0 else "dummy",
        },
        "audit_slices": {
            "evaluation_split": "test",
            "minimum_slice_size": config.minimum_slice_size,
            "slice_columns": config.audit_slice_columns,
            "evaluated_slice_count": len(slice_metrics),
            "metrics_path": str(
                config.test_slice_metrics_path.relative_to(config.project_root)
            ).replace("\\", "/"),
            "best_average_precision_slice": (
                slice_metrics.sort_values("average_precision", ascending=False).iloc[0].to_dict()
                if not slice_metrics.empty
                else None
            ),
            "worst_average_precision_slice": (
                slice_metrics.sort_values("average_precision", ascending=True).iloc[0].to_dict()
                if not slice_metrics.empty
                else None
            ),
            "interpretation": (
                "Diagnóstico agregado; os campos de auditoria não foram usados no treino."
            ),
        },
        "artifacts": {
            "model_path": str(config.model_path.relative_to(config.project_root)).replace(
                "\\", "/"
            ),
            "model_sha256": compute_sha256(config.model_path),
            "fixed_policy_path": str(
                config.fixed_policy_path.relative_to(config.project_root)
            ).replace("\\", "/"),
            "fixed_policy_sha256": compute_sha256(config.fixed_policy_path),
            "smoke_inference_probability": smoke_probability,
        },
        "versions": {
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
            "scipy": scipy.__version__,
            "joblib": joblib.__version__,
            "mlflow": mlflow.__version__,
        },
        "limitations": [
            (
                "O modelo estima associação P(conversão | contexto, canal observado), "
                "não efeito causal."
            ),
            "O teste histórico não contém recompensa contrafactual para o canal não executado.",
            (
                "Atributos de auditoria foram excluídos do modelo e devem ser usados apenas "
                "para análise de disparidade."
            ),
        ],
    }
    _write_json(report, config.metrics_path)

    should_track = config.tracking_enabled if enable_tracking is None else enable_tracking
    if should_track:
        tracking_info = _log_mlflow_run(
            config,
            report,
            [
                config.metrics_path,
                config.fixed_baseline_path,
                config.coefficients_path,
                config.validation_predictions_path,
                config.test_predictions_path,
                config.test_slice_metrics_path,
                config.model_path,
                config.fixed_policy_path,
            ],
        )
        _write_json(tracking_info, config.latest_mlflow_run_path)
    return report


def main() -> None:
    """Executa baselines, avaliação e tracking pela linha de comando."""
    parser = argparse.ArgumentParser(
        description="Treina os baselines preditivo e determinístico do M3."
    )
    parser.add_argument(
        "--config",
        default="configs/modeling.yaml",
        help="Caminho da configuração de modelagem.",
    )
    parser.add_argument(
        "--no-tracking",
        action="store_true",
        help="Desativa o registro MLflow nesta execução.",
    )
    arguments = parser.parse_args()
    report = run_m3_training(arguments.config, enable_tracking=not arguments.no_tracking)
    logistic = report["predictive_models"]["logistic_regression"]
    print(
        "M3 concluído: "
        f"ação fixa={report['fixed_policy']['best_action']}, "
        f"PR-AUC validação={logistic['validation']['average_precision']:.4f}, "
        f"PR-AUC teste={logistic['test']['average_precision']:.4f}, "
        f"gate={report['selection']['gate_passed']}."
    )


if __name__ == "__main__":
    main()
