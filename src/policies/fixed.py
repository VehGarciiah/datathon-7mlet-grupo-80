"""Baseline determinístico baseado no melhor braço histórico do treino."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from statistics import NormalDist

import pandas as pd

from src.data.contracts import DataContractError
from src.features.build_features import ACTION_COLUMN, TARGET_COLUMN
from src.policies.base import Decision


@dataclass(frozen=True)
class ActionStatistics:
    """Resume recompensa e incerteza de um braço no treino."""

    action: str
    observations: int
    conversions: int
    conversion_rate: float
    confidence_interval_lower: float
    confidence_interval_upper: float


def wilson_interval(successes: int, observations: int, z_value: float = 1.959963984540054) -> tuple[float, float]:
    """Calcula intervalo de Wilson de 95% para uma proporção binária."""
    if observations <= 0:
        return 0.0, 0.0
    rate = successes / observations
    denominator = 1 + (z_value**2 / observations)
    center = rate + (z_value**2 / (2 * observations))
    margin = z_value * math.sqrt(
        (rate * (1 - rate) / observations) + (z_value**2 / (4 * observations**2))
    )
    return (center - margin) / denominator, (center + margin) / denominator


class BestHistoricalActionPolicy:
    """Escolhe o braço de maior conversão observada somente no treino."""

    def __init__(
        self,
        action_order: list[str],
        *,
        policy_id: str = "best_historical_action",
        version: str = "1.0.0",
        confidence_level: float = 0.95,
    ) -> None:
        if not action_order or len(set(action_order)) != len(action_order):
            raise DataContractError("A ordem de ações deve ser não vazia e sem duplicatas.")
        self.action_order = tuple(action_order)
        self.policy_id = policy_id
        self.version = version
        if not 0 < confidence_level < 1:
            raise DataContractError("O nível de confiança deve estar entre 0 e 1.")
        self.confidence_level = confidence_level
        self.z_value = NormalDist().inv_cdf((1 + confidence_level) / 2)
        self.best_action: str | None = None
        self.statistics: list[ActionStatistics] = []

    def fit(self, frame: pd.DataFrame) -> "BestHistoricalActionPolicy":
        """Congela a melhor ação a partir do split recebido como treino."""
        missing = {ACTION_COLUMN, TARGET_COLUMN} - set(frame.columns)
        if missing:
            raise DataContractError(f"Colunas ausentes para ajustar a política: {sorted(missing)}.")
        if not set(frame[ACTION_COLUMN]).issubset(self.action_order):
            unexpected = sorted(set(frame[ACTION_COLUMN]) - set(self.action_order))
            raise DataContractError(f"Ações fora do contrato: {unexpected}.")
        if not set(frame[TARGET_COLUMN]).issubset({0, 1}):
            raise DataContractError("A recompensa da política deve ser binária.")

        summaries: list[ActionStatistics] = []
        for action in self.action_order:
            action_rewards = frame.loc[frame[ACTION_COLUMN].eq(action), TARGET_COLUMN]
            observations = len(action_rewards)
            if observations == 0:
                continue
            conversions = int(action_rewards.sum())
            lower, upper = wilson_interval(conversions, observations, self.z_value)
            summaries.append(
                ActionStatistics(
                    action=action,
                    observations=observations,
                    conversions=conversions,
                    conversion_rate=conversions / observations,
                    confidence_interval_lower=lower,
                    confidence_interval_upper=upper,
                )
            )
        if not summaries:
            raise DataContractError("Nenhuma ação possui observações no treino.")

        rates = {item.action: item.conversion_rate for item in summaries}
        self.best_action = max(self.action_order, key=lambda action: rates.get(action, float("-inf")))
        self.statistics = summaries
        return self

    def recommend(self, context: dict, eligible_actions: list[str]) -> Decision:
        """Usa fallback estável se o melhor braço não estiver elegível."""
        del context
        if self.best_action is None:
            raise DataContractError("A política fixa ainda não foi ajustada.")
        allowed_actions = [action for action in self.action_order if action in eligible_actions]
        if not allowed_actions:
            raise DataContractError("Nenhuma ação elegível foi fornecida.")

        used_fallback = self.best_action not in allowed_actions
        selected_action = allowed_actions[0] if used_fallback else self.best_action
        reason = (
            "Melhor canal histórico do treino indisponível; fallback elegível aplicado."
            if used_fallback
            else "Canal com maior conversão histórica calculada exclusivamente no treino."
        )
        return Decision(
            action=selected_action,
            policy_id=self.policy_id,
            policy_version=self.version,
            is_exploration=False,
            used_fallback=used_fallback,
            reason=reason,
        )

    def to_dict(self) -> dict:
        """Serializa o estado mínimo necessário para auditoria."""
        if self.best_action is None:
            raise DataContractError("A política fixa ainda não foi ajustada.")
        return {
            "policy_id": self.policy_id,
            "policy_version": self.version,
            "confidence_level": self.confidence_level,
            "action_order": list(self.action_order),
            "best_action": self.best_action,
            "fit_split": "train",
            "statistics": [asdict(item) for item in self.statistics],
        }


def evaluate_logged_replay(policy: BestHistoricalActionPolicy, frame: pd.DataFrame) -> dict:
    """Avalia somente eventos cujo canal logado coincide com a recomendação."""
    decision = policy.recommend(context={}, eligible_actions=list(policy.action_order))
    accepted = frame.loc[frame[ACTION_COLUMN].eq(decision.action)]
    conversions = int(accepted[TARGET_COLUMN].sum())
    accepted_events = len(accepted)
    return {
        "recommended_action": decision.action,
        "total_events": len(frame),
        "accepted_events": accepted_events,
        "replay_coverage": accepted_events / len(frame),
        "conversions": conversions,
        "mean_reward": conversions / accepted_events if accepted_events else 0.0,
        "cumulative_reward": conversions,
        "limitation": "Métrica observacional condicionada à coincidência com a ação histórica.",
    }
