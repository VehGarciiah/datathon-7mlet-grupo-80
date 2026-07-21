"""Contrato de schema e vocabulário da base Bank Marketing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SOURCE_COLUMNS = [
    "age",
    "job",
    "marital",
    "education",
    "default",
    "housing",
    "loan",
    "contact",
    "month",
    "day_of_week",
    "duration",
    "campaign",
    "pdays",
    "previous",
    "poutcome",
    "emp.var.rate",
    "cons.price.idx",
    "cons.conf.idx",
    "euribor3m",
    "nr.employed",
    "y",
]

COLUMN_MAPPING = {
    "age": "idade",
    "job": "profissao",
    "marital": "estado_civil",
    "education": "escolaridade",
    "default": "inadimplencia",
    "housing": "financiamento_habitacional",
    "loan": "emprestimo_pessoal",
    "contact": "canal_contato",
    "month": "mes_contato",
    "day_of_week": "dia_semana",
    "duration": "duracao_contato",
    "campaign": "contatos_campanha_atual",
    "pdays": "dias_desde_ultimo_contato",
    "previous": "contatos_campanhas_anteriores",
    "poutcome": "resultado_campanha_anterior",
    "emp.var.rate": "taxa_variacao_emprego",
    "cons.price.idx": "indice_precos_consumidor",
    "cons.conf.idx": "indice_confianca_consumidor",
    "euribor3m": "euribor_3_meses",
    "nr.employed": "numero_empregados",
    "y": "resultado",
}

CATEGORY_MAPPINGS = {
    "job": {
        "admin.": "administrativo",
        "blue-collar": "operario",
        "entrepreneur": "empreendedor",
        "housemaid": "trabalhador_domestico",
        "management": "gestao",
        "retired": "aposentado",
        "self-employed": "autonomo",
        "services": "servicos",
        "student": "estudante",
        "technician": "tecnico",
        "unemployed": "desempregado",
        "unknown": "desconhecido",
    },
    "marital": {
        "divorced": "divorciado_ou_viuvo",
        "married": "casado",
        "single": "solteiro",
        "unknown": "desconhecido",
    },
    "education": {
        "basic.4y": "basico_4_anos",
        "basic.6y": "basico_6_anos",
        "basic.9y": "basico_9_anos",
        "high.school": "ensino_medio",
        "illiterate": "analfabeto",
        "professional.course": "curso_profissionalizante",
        "university.degree": "ensino_superior",
        "unknown": "desconhecido",
    },
    "default": {"no": "nao", "unknown": "desconhecido", "yes": "sim"},
    "housing": {"no": "nao", "unknown": "desconhecido", "yes": "sim"},
    "loan": {"no": "nao", "unknown": "desconhecido", "yes": "sim"},
    "contact": {"cellular": "celular", "telephone": "telefone"},
    "month": {
        "mar": "mar",
        "apr": "abr",
        "may": "mai",
        "jun": "jun",
        "jul": "jul",
        "aug": "ago",
        "sep": "set",
        "oct": "out",
        "nov": "nov",
        "dec": "dez",
    },
    "day_of_week": {
        "mon": "seg",
        "tue": "ter",
        "wed": "qua",
        "thu": "qui",
        "fri": "sex",
    },
    "poutcome": {
        "failure": "fracasso",
        "nonexistent": "inexistente",
        "success": "sucesso",
    },
    "y": {"no": 0, "yes": 1},
}

SOURCE_CATEGORICAL_COLUMNS = list(CATEGORY_MAPPINGS)
SOURCE_NUMERIC_COLUMNS = [column for column in SOURCE_COLUMNS if column not in SOURCE_CATEGORICAL_COLUMNS]
TRANSLATED_COLUMNS = ["event_id", *COLUMN_MAPPING.values()]
TRANSLATED_BUSINESS_COLUMNS = [column for column in TRANSLATED_COLUMNS if column != "event_id"]
TRANSLATED_CATEGORY_MAPPINGS = {
    COLUMN_MAPPING[source_column]: set(mapping.values())
    for source_column, mapping in CATEGORY_MAPPINGS.items()
    if source_column != "y"
}


class DataContractError(ValueError):
    """Indica que os dados violam o contrato versionado."""


@dataclass(frozen=True)
class ValidationReport:
    """Resume controles de qualidade relevantes para auditoria."""

    row_count: int
    column_count: int
    null_cell_count: int
    duplicate_business_rows: int
    target_distribution: dict[str, int]
    unknown_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        """Converte o relatório para uma estrutura serializável."""
        return asdict(self)
