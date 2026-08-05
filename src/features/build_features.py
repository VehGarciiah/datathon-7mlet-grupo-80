"""Constrói contexto, ação, recompensa e camada exclusiva de auditoria."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.data.contracts import TRANSLATED_BUSINESS_COLUMNS, DataContractError

IDENTIFIER_COLUMN = "event_id"
ACTION_COLUMN = "canal_contato"
TARGET_COLUMN = "resultado"

CATEGORICAL_CONTEXT_COLUMNS = [
    "mes_contato",
    "dia_semana",
    "resultado_campanha_anterior",
]

NUMERIC_CONTEXT_COLUMNS = [
    "dias_desde_ultimo_contato",
    "contatos_campanhas_anteriores",
    "tentativas_anteriores_campanha_atual",
    "taxa_variacao_emprego",
    "indice_precos_consumidor",
    "indice_confianca_consumidor",
    "euribor_3_meses",
    "numero_empregados",
]

BINARY_CONTEXT_COLUMNS = ["nunca_contatado_anteriormente"]
CONTEXT_COLUMNS = [
    *CATEGORICAL_CONTEXT_COLUMNS,
    *NUMERIC_CONTEXT_COLUMNS,
    *BINARY_CONTEXT_COLUMNS,
]

AUDIT_ONLY_COLUMNS = [
    "idade",
    "profissao",
    "estado_civil",
    "escolaridade",
    "inadimplencia",
    "financiamento_habitacional",
    "emprestimo_pessoal",
]

BLOCKED_MODEL_COLUMNS = {
    "duracao_contato",
    "contatos_campanha_atual",
    ACTION_COLUMN,
    TARGET_COLUMN,
    IDENTIFIER_COLUMN,
    *AUDIT_ONLY_COLUMNS,
}


@dataclass(frozen=True)
class FeatureBuildResult:
    """Agrupa tabelas e evidências produzidas antes dos splits."""

    model_table: pd.DataFrame
    audit_table: pd.DataFrame
    removed_duplicate_event_ids: list[int]


def build_feature_tables(interim_frame: pd.DataFrame) -> FeatureBuildResult:
    """Deduplica e separa dados de modelo e auditoria sem vazamento."""
    required_columns = {IDENTIFIER_COLUMN, *TRANSLATED_BUSINESS_COLUMNS}
    missing_columns = sorted(required_columns - set(interim_frame.columns))
    if missing_columns:
        raise DataContractError(f"Colunas ausentes na camada interim: {missing_columns}.")

    # Identifica duplicatas pelo conteúdo de negócio, preservando a primeira ocorrência.
    duplicate_mask = interim_frame.duplicated(
        subset=TRANSLATED_BUSINESS_COLUMNS,
        keep="first",
    )
    removed_event_ids = interim_frame.loc[duplicate_mask, IDENTIFIER_COLUMN].astype(int).tolist()
    deduplicated_frame = interim_frame.loc[~duplicate_mask].copy()

    # Converte a sentinela 999 em indicador explícito e ausência imputável.
    never_contacted_mask = deduplicated_frame["dias_desde_ultimo_contato"].eq(999)
    deduplicated_frame["nunca_contatado_anteriormente"] = never_contacted_mask.astype("int8")
    deduplicated_frame["dias_desde_ultimo_contato"] = (
        deduplicated_frame["dias_desde_ultimo_contato"].astype("Float64").mask(never_contacted_mask)
    )

    # O valor bruto inclui o contato atual; a decisão só pode ver tentativas anteriores.
    previous_attempts = deduplicated_frame["contatos_campanha_atual"] - 1
    if previous_attempts.lt(0).any():
        raise DataContractError("A derivação de tentativas anteriores produziu valor negativo.")
    deduplicated_frame["tentativas_anteriores_campanha_atual"] = previous_attempts.astype("int64")

    model_columns = [IDENTIFIER_COLUMN, *CONTEXT_COLUMNS, ACTION_COLUMN, TARGET_COLUMN]
    model_table = deduplicated_frame.loc[:, model_columns].copy()
    audit_table = deduplicated_frame.loc[:, [IDENTIFIER_COLUMN, *AUDIT_ONLY_COLUMNS]].copy()

    leaked_context = BLOCKED_MODEL_COLUMNS.intersection(CONTEXT_COLUMNS)
    if leaked_context:
        raise DataContractError(
            f"Colunas bloqueadas chegaram ao contexto: {sorted(leaked_context)}."
        )
    if model_table[IDENTIFIER_COLUMN].duplicated().any():
        raise DataContractError("O identificador técnico ficou duplicado após a preparação.")
    if model_table[TARGET_COLUMN].isna().any() or model_table[ACTION_COLUMN].isna().any():
        raise DataContractError("Ação ou recompensa ausente após a preparação.")

    return FeatureBuildResult(
        model_table=model_table,
        audit_table=audit_table,
        removed_duplicate_event_ids=removed_event_ids,
    )
