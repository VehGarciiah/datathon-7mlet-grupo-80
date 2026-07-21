"""Pipeline do M2 para splits e preprocessing sem vazamento."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import scipy
import sklearn
import yaml
from scipy import sparse
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.data.contracts import DataContractError
from src.data.translate import compute_sha256, load_pipeline_config
from src.data.validate import validate_translated_dataset
from src.features.build_features import (
    ACTION_COLUMN,
    AUDIT_ONLY_COLUMNS,
    BINARY_CONTEXT_COLUMNS,
    CATEGORICAL_CONTEXT_COLUMNS,
    CONTEXT_COLUMNS,
    IDENTIFIER_COLUMN,
    NUMERIC_CONTEXT_COLUMNS,
    TARGET_COLUMN,
    build_feature_tables,
)


@dataclass(frozen=True)
class PreparationConfig:
    """Configuração resolvida dos outputs e do split do M2."""

    project_root: Path
    interim_path: Path
    interim_metadata_path: Path
    csv_delimiter: str
    csv_encoding: str
    train_path: Path
    validation_path: Path
    test_path: Path
    audit_path: Path
    assignments_path: Path
    metadata_path: Path
    preprocessor_path: Path
    feature_names_path: Path
    train_matrix_path: Path
    validation_matrix_path: Path
    test_matrix_path: Path
    train_size: float
    validation_size: float
    test_size: float
    random_seed: int
    expected_rows: int
    expected_interim_columns: int
    expected_duplicates: int
    expected_rows_after_deduplication: int


def _read_yaml(path: Path) -> dict[str, Any]:
    """Carrega uma configuração YAML obrigatoriamente mapeável."""
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise DataContractError(f"Configuração inválida ou vazia: {path}.")
    return content


def load_preparation_config(config_path: str | Path = "configs/data.yaml") -> PreparationConfig:
    """Resolve caminhos do M2 relativos à raiz do projeto."""
    resolved_path = Path(config_path).resolve()
    project_root = resolved_path.parent.parent
    config = _read_yaml(resolved_path)
    interim = config["interim"]
    processed = config["processed"]
    preprocessing = config["preprocessing"]
    split = config["split"]
    quality = config["quality"]

    sizes = [float(split["train_size"]), float(split["validation_size"]), float(split["test_size"])]
    if not np.isclose(sum(sizes), 1.0) or any(size <= 0 for size in sizes):
        raise DataContractError(f"Proporções de split inválidas: {sizes}.")

    return PreparationConfig(
        project_root=project_root,
        interim_path=project_root / interim["path"],
        interim_metadata_path=project_root / interim["metadata_path"],
        csv_delimiter=processed["delimiter"],
        csv_encoding=processed["encoding"],
        train_path=project_root / processed["train_path"],
        validation_path=project_root / processed["validation_path"],
        test_path=project_root / processed["test_path"],
        audit_path=project_root / processed["audit_path"],
        assignments_path=project_root / processed["split_assignments_path"],
        metadata_path=project_root / processed["metadata_path"],
        preprocessor_path=project_root / preprocessing["artifact_path"],
        feature_names_path=project_root / preprocessing["feature_names_path"],
        train_matrix_path=project_root / preprocessing["train_matrix_path"],
        validation_matrix_path=project_root / preprocessing["validation_matrix_path"],
        test_matrix_path=project_root / preprocessing["test_matrix_path"],
        train_size=sizes[0],
        validation_size=sizes[1],
        test_size=sizes[2],
        random_seed=int(split["random_seed"]),
        expected_rows=int(quality["expected_rows"]),
        expected_interim_columns=int(quality["expected_interim_columns"]),
        expected_duplicates=int(quality["expected_duplicate_business_rows"]),
        expected_rows_after_deduplication=int(quality["expected_rows_after_deduplication"]),
    )


def load_validated_interim(config: PreparationConfig) -> pd.DataFrame:
    """Confere linhagem e contrato antes de preparar qualquer feature."""
    if not config.interim_path.exists() or not config.interim_metadata_path.exists():
        raise DataContractError("Camada interim ou metadados ausentes; execute o M1 primeiro.")
    metadata = json.loads(config.interim_metadata_path.read_text(encoding="utf-8"))
    actual_hash = compute_sha256(config.interim_path)
    if actual_hash != metadata["interim"]["sha256"]:
        raise DataContractError(
            "O hash da camada interim diverge dos metadados. "
            f"Esperado={metadata['interim']['sha256']}; recebido={actual_hash}."
        )

    frame = pd.read_csv(
        config.interim_path,
        sep=config.csv_delimiter,
        encoding=config.csv_encoding,
    )
    validate_translated_dataset(
        frame,
        expected_rows=config.expected_rows,
        expected_columns=config.expected_interim_columns,
        expected_duplicates=config.expected_duplicates,
    )
    return frame


def split_model_table(
    model_table: pd.DataFrame,
    config: PreparationConfig,
) -> dict[str, pd.DataFrame]:
    """Cria splits estratificados, disjuntos e deterministicamente ordenados."""
    train_frame, remaining_frame = train_test_split(
        model_table,
        train_size=config.train_size,
        random_state=config.random_seed,
        stratify=model_table[TARGET_COLUMN],
    )
    relative_test_size = config.test_size / (config.validation_size + config.test_size)
    validation_frame, test_frame = train_test_split(
        remaining_frame,
        test_size=relative_test_size,
        random_state=config.random_seed,
        stratify=remaining_frame[TARGET_COLUMN],
    )
    splits = {
        "train": train_frame.sort_values(IDENTIFIER_COLUMN).reset_index(drop=True),
        "validation": validation_frame.sort_values(IDENTIFIER_COLUMN).reset_index(drop=True),
        "test": test_frame.sort_values(IDENTIFIER_COLUMN).reset_index(drop=True),
    }
    _validate_splits(splits, len(model_table), config.expected_rows_after_deduplication)
    return splits


def _validate_splits(
    splits: dict[str, pd.DataFrame],
    received_total: int,
    expected_total: int,
) -> None:
    """Impede sobreposição, perda de linhas ou perda de classe nos splits."""
    if received_total != expected_total:
        raise DataContractError(
            f"Total após deduplicação inesperado: {received_total}; esperado={expected_total}."
        )
    id_sets = {name: set(frame[IDENTIFIER_COLUMN]) for name, frame in splits.items()}
    if id_sets["train"] & id_sets["validation"] or id_sets["train"] & id_sets["test"]:
        raise DataContractError("Há event_id compartilhado entre treino e outro split.")
    if id_sets["validation"] & id_sets["test"]:
        raise DataContractError("Há event_id compartilhado entre validação e teste.")
    if sum(len(ids) for ids in id_sets.values()) != expected_total:
        raise DataContractError("Os splits perderam ou duplicaram registros.")
    for name, frame in splits.items():
        if set(frame[TARGET_COLUMN]) != {0, 1}:
            raise DataContractError(f"O split '{name}' não contém as duas classes.")


def create_context_preprocessor() -> ColumnTransformer:
    """Define transformações sem ajustá-las em validação ou teste."""
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "encoder",
                OneHotEncoder(handle_unknown="ignore", sparse_output=True, dtype=np.float32),
            ),
        ]
    )
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("categorical", categorical_pipeline, CATEGORICAL_CONTEXT_COLUMNS),
            ("numeric", numeric_pipeline, NUMERIC_CONTEXT_COLUMNS),
            ("binary", "passthrough", BINARY_CONTEXT_COLUMNS),
        ],
        remainder="drop",
        sparse_threshold=1.0,
        verbose_feature_names_out=False,
    )


def fit_and_transform_splits(
    splits: dict[str, pd.DataFrame],
) -> tuple[ColumnTransformer, dict[str, sparse.csr_matrix], list[str]]:
    """Ajusta no treino e apenas transforma validação e teste."""
    preprocessor = create_context_preprocessor()
    train_context = splits["train"].loc[:, CONTEXT_COLUMNS]
    preprocessor.fit(train_context)

    matrices = {
        name: sparse.csr_matrix(preprocessor.transform(frame.loc[:, CONTEXT_COLUMNS]))
        for name, frame in splits.items()
    }
    feature_names = preprocessor.get_feature_names_out().tolist()
    return preprocessor, matrices, feature_names


def _write_csv_atomically(frame: pd.DataFrame, path: Path, config: PreparationConfig) -> None:
    """Grava uma tabela sem expor arquivo parcial."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(
        temporary_path,
        sep=config.csv_delimiter,
        encoding=config.csv_encoding,
        index=False,
        lineterminator="\n",
    )
    temporary_path.replace(path)


def _write_json_atomically(content: dict[str, Any] | list[str], path: Path) -> None:
    """Grava JSON estável para auditoria e consumo futuro."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _write_joblib_atomically(content: dict[str, Any], path: Path) -> None:
    """Serializa o preprocessing somente após ajuste no treino."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    joblib.dump(content, temporary_path)
    temporary_path.replace(path)


def _write_sparse_matrix_atomically(matrix: sparse.csr_matrix, path: Path) -> None:
    """Persiste a matriz esparsa sem risco de extensão automática ambígua."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(path.name + ".tmp.npz")
    sparse.save_npz(temporary_path, matrix)
    temporary_path.replace(path)


def _relative_path(path: Path, project_root: Path) -> str:
    """Normaliza caminhos dos metadados para uso multiplataforma."""
    return str(path.relative_to(project_root)).replace("\\", "/")


def _split_summary(frame: pd.DataFrame) -> dict[str, Any]:
    """Resume tamanho e prevalência sem arredondar a evidência bruta."""
    distribution = frame[TARGET_COLUMN].value_counts().sort_index().to_dict()
    return {
        "row_count": len(frame),
        "target_distribution": {str(key): int(value) for key, value in distribution.items()},
        "positive_rate": float(frame[TARGET_COLUMN].mean()),
    }


def build_processed_datasets(
    config_path: str | Path = "configs/data.yaml",
) -> dict[str, Any]:
    """Executa o M2 completo e retorna seus metadados auditáveis."""
    config = load_preparation_config(config_path)
    interim_frame = load_validated_interim(config)
    feature_result = build_feature_tables(interim_frame)
    splits = split_model_table(feature_result.model_table, config)
    preprocessor, matrices, feature_names = fit_and_transform_splits(splits)

    output_paths = {
        "train": config.train_path,
        "validation": config.validation_path,
        "test": config.test_path,
    }
    for name, path in output_paths.items():
        _write_csv_atomically(splits[name], path, config)

    assignments = pd.concat(
        [
            frame[[IDENTIFIER_COLUMN]].assign(split=name)
            for name, frame in splits.items()
        ],
        ignore_index=True,
    ).sort_values(IDENTIFIER_COLUMN)
    _write_csv_atomically(assignments, config.assignments_path, config)

    audit_table = feature_result.audit_table.merge(
        assignments,
        on=IDENTIFIER_COLUMN,
        how="inner",
        validate="one_to_one",
    ).sort_values(IDENTIFIER_COLUMN)
    _write_csv_atomically(audit_table, config.audit_path, config)

    artifact = {
        "schema_version": "1.0.0",
        "fit_split": "train",
        "context_columns": CONTEXT_COLUMNS,
        "categorical_columns": CATEGORICAL_CONTEXT_COLUMNS,
        "numeric_columns": NUMERIC_CONTEXT_COLUMNS,
        "binary_columns": BINARY_CONTEXT_COLUMNS,
        "feature_names": feature_names,
        "preprocessor": preprocessor,
    }
    _write_joblib_atomically(artifact, config.preprocessor_path)
    _write_json_atomically(feature_names, config.feature_names_path)
    matrix_paths = {
        "train": config.train_matrix_path,
        "validation": config.validation_matrix_path,
        "test": config.test_matrix_path,
    }
    for name, path in matrix_paths.items():
        _write_sparse_matrix_atomically(matrices[name], path)

    metadata = {
        "pipeline_schema_version": "1.0.0",
        "input": {
            "path": _relative_path(config.interim_path, config.project_root),
            "sha256": compute_sha256(config.interim_path),
            "row_count": len(interim_frame),
        },
        "deduplication": {
            "business_rows_removed": len(feature_result.removed_duplicate_event_ids),
            "removed_event_ids": feature_result.removed_duplicate_event_ids,
            "remaining_rows": len(feature_result.model_table),
            "keep": "first_by_source_order",
        },
        "contracts": {
            "identifier_column": IDENTIFIER_COLUMN,
            "context_columns": CONTEXT_COLUMNS,
            "action_column": ACTION_COLUMN,
            "target_column": TARGET_COLUMN,
            "audit_only_columns": AUDIT_ONLY_COLUMNS,
            "blocked_direct_columns": ["duracao_contato", "contatos_campanha_atual"],
        },
        "split": {
            "random_seed": config.random_seed,
            "stratified_by": TARGET_COLUMN,
            "proportions": {
                "train": config.train_size,
                "validation": config.validation_size,
                "test": config.test_size,
            },
            "summaries": {name: _split_summary(frame) for name, frame in splits.items()},
        },
        "preprocessing": {
            "fit_split": "train",
            "feature_count": len(feature_names),
            "feature_names": feature_names,
            "matrix_shapes": {
                name: [int(value) for value in matrix.shape]
                for name, matrix in matrices.items()
            },
            "artifact_path": _relative_path(config.preprocessor_path, config.project_root),
            "artifact_sha256": compute_sha256(config.preprocessor_path),
            "versions": {
                "pandas": pd.__version__,
                "scikit_learn": sklearn.__version__,
                "scipy": scipy.__version__,
                "joblib": joblib.__version__,
            },
        },
        "outputs": {
            name: {
                "path": _relative_path(path, config.project_root),
                "sha256": compute_sha256(path),
            }
            for name, path in {
                **output_paths,
                "audit": config.audit_path,
                "split_assignments": config.assignments_path,
            }.items()
        },
    }
    _write_json_atomically(metadata, config.metadata_path)
    return metadata


def main() -> None:
    """Executa o pipeline do M2 por linha de comando."""
    parser = argparse.ArgumentParser(description="Prepara splits e preprocessing do Datathon.")
    parser.add_argument(
        "--config",
        default="configs/data.yaml",
        help="Caminho da configuração do pipeline de dados.",
    )
    arguments = parser.parse_args()
    metadata = build_processed_datasets(arguments.config)
    summaries = metadata["split"]["summaries"]
    print(
        "M2 concluído: "
        f"treino={summaries['train']['row_count']}, "
        f"validação={summaries['validation']['row_count']}, "
        f"teste={summaries['test']['row_count']}, "
        f"features={metadata['preprocessing']['feature_count']}."
    )


if __name__ == "__main__":
    main()
