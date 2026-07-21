"""Pipeline reproduzível para traduzir a base bruta para PT-BR."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.data.contracts import (
    CATEGORY_MAPPINGS,
    COLUMN_MAPPING,
    SOURCE_COLUMNS,
    TRANSLATED_COLUMNS,
    DataContractError,
)
from src.data.validate import validate_raw_dataset, validate_translated_dataset


@dataclass(frozen=True)
class DataPipelineConfig:
    """Reúne caminhos e expectativas carregados dos contratos YAML."""

    project_root: Path
    source_path: Path
    source_sha256: str
    source_delimiter: str
    source_encoding: str
    interim_path: Path
    metadata_path: Path
    interim_delimiter: str
    interim_encoding: str
    expected_rows: int
    expected_source_columns: int
    expected_interim_columns: int
    expected_duplicates: int
    expected_source_target_distribution: dict[str, int]
    expected_interim_target_distribution: dict[int, int]


def compute_sha256(path: Path) -> str:
    """Calcula o hash do arquivo sem carregá-lo integralmente em memória."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_yaml(path: Path) -> dict[str, Any]:
    """Carrega um YAML e rejeita documento vazio ou não mapeável."""
    with path.open("r", encoding="utf-8") as stream:
        content = yaml.safe_load(stream)
    if not isinstance(content, dict):
        raise DataContractError(f"Configuração YAML inválida ou vazia: {path}.")
    return content


def load_pipeline_config(config_path: str | Path = "configs/data.yaml") -> DataPipelineConfig:
    """Resolve a configuração operacional e o contrato factual do experimento."""
    resolved_config_path = Path(config_path).resolve()
    project_root = resolved_config_path.parent.parent
    data_config = _read_yaml(resolved_config_path)
    experiment_path = project_root / data_config["experiment_config_path"]
    experiment_config = _read_yaml(experiment_path)

    source = experiment_config["dataset"]["local_snapshot"]
    reward = experiment_config["reward"]
    interim = data_config["interim"]
    quality = data_config["quality"]
    interim_target_distribution = {
        int(key): int(value)
        for key, value in quality["expected_target_distribution"].items()
    }
    return DataPipelineConfig(
        project_root=project_root,
        source_path=project_root / source["path"],
        source_sha256=str(source["sha256"]).lower(),
        source_delimiter=source["delimiter"],
        source_encoding=source["encoding"],
        interim_path=project_root / interim["path"],
        metadata_path=project_root / interim["metadata_path"],
        interim_delimiter=interim["delimiter"],
        interim_encoding=interim["encoding"],
        expected_rows=int(quality["expected_rows"]),
        expected_source_columns=int(quality["expected_source_columns"]),
        expected_interim_columns=int(quality["expected_interim_columns"]),
        expected_duplicates=int(quality["expected_duplicate_business_rows"]),
        expected_source_target_distribution={
            str(reward["negative_source_value"]): interim_target_distribution[0],
            str(reward["positive_source_value"]): interim_target_distribution[1],
        },
        expected_interim_target_distribution=interim_target_distribution,
    )


def load_raw_dataset(config: DataPipelineConfig) -> pd.DataFrame:
    """Verifica a integridade e carrega o snapshot bruto imutável."""
    if not config.source_path.exists():
        raise DataContractError(f"Arquivo bruto não encontrado: {config.source_path}.")

    actual_hash = compute_sha256(config.source_path)
    if actual_hash != config.source_sha256:
        raise DataContractError(
            "O hash do arquivo bruto diverge do contrato. "
            f"Esperado={config.source_sha256}; recebido={actual_hash}."
        )

    return pd.read_csv(
        config.source_path,
        sep=config.source_delimiter,
        encoding=config.source_encoding,
    )


def translate_dataset_to_ptbr(source_frame: pd.DataFrame) -> pd.DataFrame:
    """Traduz colunas e categorias sem alterar o DataFrame de origem."""
    if list(source_frame.columns) != SOURCE_COLUMNS:
        raise DataContractError(
            "Não é possível traduzir: as colunas brutas divergem do contrato."
        )

    # Cria uma cópia profunda para preservar a camada bruta em memória.
    translated_frame = source_frame.copy(deep=True)

    # Traduz cada categoria antes de renomear as colunas.
    for source_column, mapping in CATEGORY_MAPPINGS.items():
        original_values = translated_frame[source_column]
        translated_values = original_values.map(mapping)
        unmapped_mask = original_values.notna() & translated_values.isna()
        if unmapped_mask.any():
            unexpected = sorted(original_values.loc[unmapped_mask].astype(str).unique())
            raise DataContractError(
                f"Categorias sem tradução em '{source_column}': {unexpected}."
            )
        translated_frame[source_column] = translated_values

    # Renomeia as colunas somente após validar todo o vocabulário.
    translated_frame = translated_frame.rename(columns=COLUMN_MAPPING)

    # Cria um identificador técnico estável que nunca poderá ser feature.
    translated_frame.insert(0, "event_id", range(1, len(translated_frame) + 1))
    translated_frame["resultado"] = translated_frame["resultado"].astype("int8")
    return translated_frame.loc[:, TRANSLATED_COLUMNS]


def _write_dataframe_atomically(frame: pd.DataFrame, config: DataPipelineConfig) -> None:
    """Evita deixar um CSV parcial quando a gravação for interrompida."""
    config.interim_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config.interim_path.with_suffix(config.interim_path.suffix + ".tmp")
    frame.to_csv(
        temporary_path,
        sep=config.interim_delimiter,
        encoding=config.interim_encoding,
        index=False,
        lineterminator="\n",
    )
    temporary_path.replace(config.interim_path)


def _write_metadata_atomically(metadata: dict[str, Any], config: DataPipelineConfig) -> None:
    """Grava a evidência de paridade e linhagem em JSON determinístico."""
    config.metadata_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config.metadata_path.with_suffix(config.metadata_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(config.metadata_path)


def build_interim_dataset(
    config_path: str | Path = "configs/data.yaml",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Executa hash, validação, tradução e persistência da camada interim."""
    config = load_pipeline_config(config_path)
    source_frame = load_raw_dataset(config)
    raw_report = validate_raw_dataset(
        source_frame,
        expected_rows=config.expected_rows,
        expected_columns=config.expected_source_columns,
        expected_duplicates=config.expected_duplicates,
        expected_target_distribution=config.expected_source_target_distribution,
    )

    translated_frame = translate_dataset_to_ptbr(source_frame)
    translated_report = validate_translated_dataset(
        translated_frame,
        expected_rows=config.expected_rows,
        expected_columns=config.expected_interim_columns,
        expected_duplicates=config.expected_duplicates,
        expected_target_distribution=config.expected_interim_target_distribution,
    )
    _write_dataframe_atomically(translated_frame, config)

    metadata = {
        "pipeline_schema_version": "1.0.0",
        "source": {
            "path": str(config.source_path.relative_to(config.project_root)).replace("\\", "/"),
            "sha256": config.source_sha256,
            "validation": raw_report.to_dict(),
        },
        "interim": {
            "path": str(config.interim_path.relative_to(config.project_root)).replace("\\", "/"),
            "sha256": compute_sha256(config.interim_path),
            "validation": translated_report.to_dict(),
        },
        "translation": {
            "language": "pt-BR",
            "mapped_source_columns": len(COLUMN_MAPPING),
            "event_id_added": True,
            "business_rows_removed": 0,
        },
    }
    _write_metadata_atomically(metadata, config)
    return translated_frame, metadata


def main() -> None:
    """Disponibiliza a construção da camada interim por linha de comando."""
    parser = argparse.ArgumentParser(description="Traduz e valida a base Bank Marketing.")
    parser.add_argument(
        "--config",
        default="configs/data.yaml",
        help="Caminho da configuração do pipeline de dados.",
    )
    arguments = parser.parse_args()
    translated_frame, metadata = build_interim_dataset(arguments.config)
    print(
        "Camada interim gerada com sucesso: "
        f"{len(translated_frame)} registros, {len(translated_frame.columns)} colunas, "
        f"SHA-256 {metadata['interim']['sha256']}."
    )


if __name__ == "__main__":
    main()
