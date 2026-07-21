"""Validações fail-fast das camadas bruta e canônica."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from src.data.contracts import (
    CATEGORY_MAPPINGS,
    SOURCE_COLUMNS,
    SOURCE_NUMERIC_COLUMNS,
    TRANSLATED_BUSINESS_COLUMNS,
    TRANSLATED_CATEGORY_MAPPINGS,
    TRANSLATED_COLUMNS,
    DataContractError,
    ValidationReport,
)


def _raise_if_errors(errors: Iterable[str]) -> None:
    """Agrupa falhas para reduzir ciclos de correção do contrato."""
    error_list = list(errors)
    if error_list:
        details = "\n- ".join(error_list)
        raise DataContractError(f"Falha na validação dos dados:\n- {details}")


def _unknown_counts(frame: pd.DataFrame, unknown_value: str) -> dict[str, int]:
    """Conta desconhecidos apenas nas colunas que aceitam essa categoria."""
    return {
        column: int(frame[column].eq(unknown_value).sum())
        for column in frame.columns
        if frame[column].dtype == "object" or isinstance(frame[column].dtype, pd.StringDtype)
        if frame[column].eq(unknown_value).any()
    }


def validate_raw_dataset(
    frame: pd.DataFrame,
    *,
    expected_rows: int = 41188,
    expected_columns: int = 21,
    expected_duplicates: int = 12,
    expected_target_distribution: dict[str, int] | None = None,
) -> ValidationReport:
    """Valida o snapshot original antes de qualquer tradução."""
    errors: list[str] = []

    if list(frame.columns) != SOURCE_COLUMNS:
        errors.append(
            "As colunas brutas ou sua ordem divergem do contrato. "
            f"Esperado={SOURCE_COLUMNS}; recebido={list(frame.columns)}."
        )
    if frame.shape != (expected_rows, expected_columns):
        errors.append(
            f"Dimensão bruta inesperada: {frame.shape}; "
            f"esperado=({expected_rows}, {expected_columns})."
        )

    null_cell_count = int(frame.isna().sum().sum())
    if null_cell_count:
        errors.append(f"Foram encontradas {null_cell_count} células nulas na fonte.")

    for column, mapping in CATEGORY_MAPPINGS.items():
        if column not in frame.columns:
            continue
        received = set(frame[column].dropna().unique())
        expected = set(mapping)
        if received != expected:
            errors.append(
                f"Categorias inesperadas em '{column}': "
                f"ausentes={sorted(expected - received)}; novas={sorted(received - expected)}."
            )

    for column in SOURCE_NUMERIC_COLUMNS:
        if column not in frame.columns:
            continue
        converted = pd.to_numeric(frame[column], errors="coerce")
        invalid_count = int(converted.isna().sum())
        if invalid_count or not np.isfinite(converted).all():
            errors.append(f"A coluna numérica '{column}' contém valores inválidos.")

    if "age" in frame and not frame["age"].between(0, 120).all():
        errors.append("A coluna 'age' contém valor fora da faixa plausível 0–120.")
    if "duration" in frame and frame["duration"].lt(0).any():
        errors.append("A coluna 'duration' contém valor negativo.")
    if "campaign" in frame and frame["campaign"].lt(1).any():
        errors.append("A coluna 'campaign' deve ser maior ou igual a 1.")
    if "pdays" in frame and frame["pdays"].lt(0).any():
        errors.append("A coluna 'pdays' contém valor negativo.")
    if "previous" in frame and frame["previous"].lt(0).any():
        errors.append("A coluna 'previous' contém valor negativo.")

    duplicate_count = int(frame.duplicated().sum())
    if duplicate_count != expected_duplicates:
        errors.append(
            f"Quantidade de duplicatas inesperada: {duplicate_count}; "
            f"esperado={expected_duplicates}."
        )

    expected_target_distribution = expected_target_distribution or {"no": 36548, "yes": 4640}
    target_distribution = frame["y"].value_counts().sort_index().to_dict() if "y" in frame else {}
    if target_distribution != expected_target_distribution:
        errors.append(f"Distribuição do target bruto inesperada: {target_distribution}.")

    _raise_if_errors(errors)
    return ValidationReport(
        row_count=len(frame),
        column_count=len(frame.columns),
        null_cell_count=null_cell_count,
        duplicate_business_rows=duplicate_count,
        target_distribution={str(key): int(value) for key, value in target_distribution.items()},
        unknown_counts=_unknown_counts(frame, "unknown"),
    )


def validate_translated_dataset(
    frame: pd.DataFrame,
    *,
    expected_rows: int = 41188,
    expected_columns: int = 22,
    expected_duplicates: int = 12,
    expected_target_distribution: dict[int, int] | None = None,
) -> ValidationReport:
    """Valida a paridade e o vocabulário da camada canônica PT-BR."""
    errors: list[str] = []

    if list(frame.columns) != TRANSLATED_COLUMNS:
        errors.append(
            "As colunas traduzidas ou sua ordem divergem do contrato. "
            f"Esperado={TRANSLATED_COLUMNS}; recebido={list(frame.columns)}."
        )
    if frame.shape != (expected_rows, expected_columns):
        errors.append(
            f"Dimensão traduzida inesperada: {frame.shape}; "
            f"esperado=({expected_rows}, {expected_columns})."
        )

    null_cell_count = int(frame.isna().sum().sum())
    if null_cell_count:
        errors.append(f"Foram encontradas {null_cell_count} células nulas após a tradução.")

    if "event_id" in frame.columns:
        expected_ids = pd.Series(range(1, len(frame) + 1), dtype="int64")
        received_ids = frame["event_id"].reset_index(drop=True).astype("int64")
        if not received_ids.equals(expected_ids):
            errors.append("'event_id' não é único, estável e sequencial a partir de 1.")

    for column, expected_values in TRANSLATED_CATEGORY_MAPPINGS.items():
        if column not in frame.columns:
            continue
        received = set(frame[column].dropna().unique())
        if received != expected_values:
            errors.append(
                f"Categorias canônicas inesperadas em '{column}': "
                f"ausentes={sorted(expected_values - received)}; "
                f"novas={sorted(received - expected_values)}."
            )

    duplicate_count = (
        int(frame.duplicated(subset=TRANSLATED_BUSINESS_COLUMNS).sum())
        if set(TRANSLATED_BUSINESS_COLUMNS).issubset(frame.columns)
        else -1
    )
    if duplicate_count != expected_duplicates:
        errors.append(
            f"Paridade de duplicatas violada: {duplicate_count}; esperado={expected_duplicates}."
        )

    expected_target_distribution = expected_target_distribution or {0: 36548, 1: 4640}
    target_distribution = (
        frame["resultado"].value_counts().sort_index().to_dict()
        if "resultado" in frame.columns
        else {}
    )
    if target_distribution != expected_target_distribution:
        errors.append(f"Distribuição do target traduzido inesperada: {target_distribution}.")

    _raise_if_errors(errors)
    return ValidationReport(
        row_count=len(frame),
        column_count=len(frame.columns),
        null_cell_count=null_cell_count,
        duplicate_business_rows=duplicate_count,
        target_distribution={str(key): int(value) for key, value in target_distribution.items()},
        unknown_counts=_unknown_counts(frame, "desconhecido"),
    )
