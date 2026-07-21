"""Testes do contrato e da tradução EN → PT-BR."""

from __future__ import annotations

import pandas as pd
import pytest

from src.data.contracts import DataContractError, TRANSLATED_COLUMNS
from src.data.translate import (
    load_pipeline_config,
    load_raw_dataset,
    translate_dataset_to_ptbr,
)
from src.data.validate import validate_raw_dataset, validate_translated_dataset


@pytest.fixture(scope="module")
def raw_frame() -> pd.DataFrame:
    """Carrega o snapshot real uma única vez para os testes de paridade."""
    config = load_pipeline_config("configs/data.yaml")
    return load_raw_dataset(config)


def test_raw_snapshot_matches_contract(raw_frame: pd.DataFrame) -> None:
    """Garante que dimensão, categorias, target e duplicatas não mudaram."""
    report = validate_raw_dataset(raw_frame)
    assert report.row_count == 41188
    assert report.column_count == 21
    assert report.duplicate_business_rows == 12
    assert report.target_distribution == {"no": 36548, "yes": 4640}


def test_translation_preserves_source_and_business_rows(raw_frame: pd.DataFrame) -> None:
    """Comprova que a função não altera a fonte nem remove observações no M1."""
    source_before = raw_frame.copy(deep=True)
    translated_frame = translate_dataset_to_ptbr(raw_frame)

    pd.testing.assert_frame_equal(raw_frame, source_before)
    assert len(translated_frame) == len(raw_frame)
    assert list(translated_frame.columns) == TRANSLATED_COLUMNS
    assert translated_frame["event_id"].tolist() == list(range(1, 41189))


def test_translated_vocabulary_and_target_match_contract(raw_frame: pd.DataFrame) -> None:
    """Valida o vocabulário PT-BR e a paridade da recompensa."""
    translated_frame = translate_dataset_to_ptbr(raw_frame)
    report = validate_translated_dataset(translated_frame)

    assert report.target_distribution == {"0": 36548, "1": 4640}
    assert set(translated_frame["canal_contato"]) == {"celular", "telefone"}
    assert set(translated_frame["resultado"]) == {0, 1}
    assert report.duplicate_business_rows == 12


def test_translation_rejects_unmapped_category(raw_frame: pd.DataFrame) -> None:
    """Impede que uma categoria nova seja convertida silenciosamente em nulo."""
    invalid_frame = raw_frame.copy(deep=True)
    invalid_frame.loc[0, "job"] = "categoria_nova"

    with pytest.raises(DataContractError, match="Categorias sem tradução"):
        translate_dataset_to_ptbr(invalid_frame)


def test_validation_rejects_missing_leakage_column(raw_frame: pd.DataFrame) -> None:
    """Detecta alterações não versionadas até mesmo em campos bloqueados."""
    invalid_frame = raw_frame.drop(columns=["duration"])

    with pytest.raises(DataContractError, match="colunas brutas"):
        validate_raw_dataset(invalid_frame)
