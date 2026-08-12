"""Schemas Pydantic estritos do contrato HTTP do M5."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Rejeita campos silenciosos e mantém contrato previsível."""

    model_config = ConfigDict(extra="forbid")


class Action(str, Enum):
    """Braços canônicos permitidos pelo contrato de decisão."""

    CELLULAR = "celular"
    TELEPHONE = "telefone"


class Month(str, Enum):
    """Meses observados no conjunto de referência traduzido."""

    MAR = "mar"
    APR = "abr"
    MAY = "mai"
    JUN = "jun"
    JUL = "jul"
    AUG = "ago"
    SEP = "set"
    OCT = "out"
    NOV = "nov"
    DEC = "dez"


class Weekday(str, Enum):
    """Dias úteis observados no conjunto de referência."""

    MONDAY = "seg"
    TUESDAY = "ter"
    WEDNESDAY = "qua"
    THURSDAY = "qui"
    FRIDAY = "sex"


class PreviousOutcome(str, Enum):
    """Resultados canônicos da campanha anterior."""

    FAILURE = "fracasso"
    NONEXISTENT = "inexistente"
    SUCCESS = "sucesso"


class RecommendationContext(StrictModel):
    """Contexto pré-decisão com faixas derivadas do treino versionado."""

    mes_contato: Month
    dia_semana: Weekday
    resultado_campanha_anterior: PreviousOutcome
    dias_desde_ultimo_contato: Annotated[float | None, Field(ge=0, le=27)]
    contatos_campanhas_anteriores: Annotated[int, Field(ge=0, le=6)]
    tentativas_anteriores_campanha_atual: Annotated[int, Field(ge=0, le=55)]
    taxa_variacao_emprego: Annotated[float, Field(ge=-3.4, le=1.4)]
    indice_precos_consumidor: Annotated[float, Field(ge=92.201, le=94.767)]
    indice_confianca_consumidor: Annotated[float, Field(ge=-50.8, le=-26.9)]
    euribor_3_meses: Annotated[float, Field(ge=0.634, le=5.045)]
    numero_empregados: Annotated[float, Field(ge=4963.6, le=5228.1)]
    nunca_contatado_anteriormente: Literal[0, 1]

    @model_validator(mode="after")
    def validate_previous_contact_consistency(self) -> "RecommendationContext":
        """Mantém coerência entre indicador e dias desde o contato anterior."""
        if self.nunca_contatado_anteriormente == 1 and self.dias_desde_ultimo_contato is not None:
            raise ValueError(
                "dias_desde_ultimo_contato deve ser nulo quando nunca houve contato anterior."
            )
        if self.nunca_contatado_anteriormente == 0 and self.dias_desde_ultimo_contato is None:
            raise ValueError(
                "dias_desde_ultimo_contato é obrigatório quando houve contato anterior."
            )
        return self


class RecommendationRequest(StrictModel):
    """Solicita uma decisão apenas para oportunidade comprovadamente elegível."""

    context: RecommendationContext
    eligible_actions: Annotated[list[Action], Field(min_length=1, max_length=2)]
    contact_authorized: bool
    do_not_contact: bool
    targeting_key: Annotated[str | None, Field(min_length=1, max_length=128)] = None

    @model_validator(mode="after")
    def validate_unique_actions(self) -> "RecommendationRequest":
        """Impede peso acidental causado por ação elegível duplicada."""
        if len(set(self.eligible_actions)) != len(self.eligible_actions):
            raise ValueError("eligible_actions não pode conter ações duplicadas.")
        return self


class RecommendationResponse(StrictModel):
    """Retorna decisão auditável sem expor atributos de risco."""

    recommendation_id: UUID
    recommended_action: Action
    policy_id: str
    policy_version: str
    model_version: str
    is_exploration: bool
    used_fallback: bool
    reason: str
    evidence: dict[str, Any]
    created_at: datetime


class FeedbackRequest(StrictModel):
    """Vincula recompensa binária a uma recomendação existente."""

    recommendation_id: UUID
    reward: Literal[0, 1]
    observed_at: datetime

    @model_validator(mode="after")
    def validate_timezone(self) -> "FeedbackRequest":
        """Exige timestamp absoluto para impedir atribuição ambígua."""
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at deve conter fuso horário explícito.")
        return self


class FeedbackResponse(StrictModel):
    """Explica se o feedback foi novo, duplicado ou usado no aprendizado."""

    recommendation_id: UUID
    status: Literal["recorded", "duplicate"]
    learning_applied: bool
    reason: str


class HealthResponse(StrictModel):
    """Representa vida do processo sem depender dos artefatos."""

    status: Literal["alive"]
    service: str
    timestamp: datetime


class ReadyResponse(StrictModel):
    """Expõe somente metadados técnicos necessários para operação."""

    status: Literal["ready", "not_ready"]
    active_policy_id: str | None
    active_policy_version: str | None
    policy_mode: str | None
    model_version: str | None
    m3_run_id: str | None
    m4_run_id: str | None
    fallback_reason: str | None
    error: str | None
