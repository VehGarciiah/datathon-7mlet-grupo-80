"""Testes de deduplicação, engenharia e separação de responsabilidades."""

from __future__ import annotations

import pandas as pd

from src.data.prepare import load_preparation_config, load_validated_interim, split_model_table
from src.features.build_features import (
    ACTION_COLUMN,
    AUDIT_ONLY_COLUMNS,
    BLOCKED_MODEL_COLUMNS,
    CONTEXT_COLUMNS,
    IDENTIFIER_COLUMN,
    TARGET_COLUMN,
    build_feature_tables,
)


def _load_feature_result():
    """Carrega os dados reais para validar as regras do snapshot."""
    config = load_preparation_config("configs/data.yaml")
    interim_frame = load_validated_interim(config)
    return config, interim_frame, build_feature_tables(interim_frame)


def test_deduplication_preserves_lineage_and_expected_count() -> None:
    """Remove somente as 12 repetições e preserva o primeiro event_id."""
    config, interim_frame, result = _load_feature_result()

    assert len(result.removed_duplicate_event_ids) == 12
    assert len(result.model_table) == config.expected_rows_after_deduplication
    assert len(result.model_table) == len(interim_frame) - 12
    assert not result.model_table[IDENTIFIER_COLUMN].duplicated().any()


def test_model_context_excludes_leakage_action_target_and_audit() -> None:
    """Comprova que somente contexto pré-decisão chega ao preprocessing."""
    _, _, result = _load_feature_result()
    model_columns = set(result.model_table.columns)

    assert set(CONTEXT_COLUMNS).issubset(model_columns)
    assert ACTION_COLUMN in model_columns
    assert TARGET_COLUMN in model_columns
    assert IDENTIFIER_COLUMN in model_columns
    assert "duracao_contato" not in model_columns
    assert "contatos_campanha_atual" not in model_columns
    assert not set(AUDIT_ONLY_COLUMNS).intersection(model_columns)
    assert not BLOCKED_MODEL_COLUMNS.intersection(CONTEXT_COLUMNS)


def test_sentinel_and_current_attempt_are_converted_to_pre_decision_features() -> None:
    """Valida as duas derivações que evitam semântica incorreta e vazamento."""
    _, interim_frame, result = _load_feature_result()
    retained_ids = set(result.model_table[IDENTIFIER_COLUMN])
    retained_interim = interim_frame[interim_frame[IDENTIFIER_COLUMN].isin(retained_ids)].copy()
    prepared_by_id = result.model_table.set_index(IDENTIFIER_COLUMN)
    source_by_id = retained_interim.set_index(IDENTIFIER_COLUMN)

    never_contacted = source_by_id["dias_desde_ultimo_contato"].eq(999)
    assert prepared_by_id.loc[never_contacted, "nunca_contatado_anteriormente"].eq(1).all()
    assert prepared_by_id.loc[never_contacted, "dias_desde_ultimo_contato"].isna().all()
    expected_attempts = source_by_id["contatos_campanha_atual"] - 1
    pd.testing.assert_series_equal(
        prepared_by_id["tentativas_anteriores_campanha_atual"],
        expected_attempts.rename("tentativas_anteriores_campanha_atual"),
        check_dtype=False,
    )


def test_splits_are_deterministic_disjoint_and_stratified() -> None:
    """Repete o split para confirmar estabilidade e ausência de sobreposição."""
    config, _, result = _load_feature_result()
    first = split_model_table(result.model_table, config)
    second = split_model_table(result.model_table, config)

    for name in first:
        pd.testing.assert_frame_equal(first[name], second[name])
        assert set(first[name][TARGET_COLUMN]) == {0, 1}

    train_ids = set(first["train"][IDENTIFIER_COLUMN])
    validation_ids = set(first["validation"][IDENTIFIER_COLUMN])
    test_ids = set(first["test"][IDENTIFIER_COLUMN])
    assert train_ids.isdisjoint(validation_ids)
    assert train_ids.isdisjoint(test_ids)
    assert validation_ids.isdisjoint(test_ids)
    assert len(train_ids | validation_ids | test_ids) == config.expected_rows_after_deduplication
