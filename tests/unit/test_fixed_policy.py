"""Testes do baseline determinístico de melhor ação histórica."""

from __future__ import annotations

import pandas as pd
import pytest

from src.data.contracts import DataContractError
from src.features.build_features import ACTION_COLUMN, TARGET_COLUMN
from src.policies.fixed import BestHistoricalActionPolicy, evaluate_logged_replay, wilson_interval


@pytest.fixture
def training_frame() -> pd.DataFrame:
    """Cria recompensas em que celular é inequivocamente o melhor braço."""
    return pd.DataFrame(
        {
            ACTION_COLUMN: ["celular"] * 5 + ["telefone"] * 5,
            TARGET_COLUMN: [1, 1, 1, 0, 0, 1, 0, 0, 0, 0],
        }
    )


def test_policy_selects_best_training_action_and_stable_fallback(training_frame: pd.DataFrame) -> None:
    """Congela celular e usa telefone apenas se celular não for elegível."""
    policy = BestHistoricalActionPolicy(["celular", "telefone"]).fit(training_frame)

    decision = policy.recommend({}, ["celular", "telefone"])
    fallback = policy.recommend({}, ["telefone"])
    assert policy.best_action == "celular"
    assert decision.action == "celular"
    assert decision.used_fallback is False
    assert fallback.action == "telefone"
    assert fallback.used_fallback is True


def test_policy_requires_fit_and_at_least_one_eligible_action(training_frame: pd.DataFrame) -> None:
    """Impede recomendação sem estado ou fora do conjunto permitido."""
    policy = BestHistoricalActionPolicy(["celular", "telefone"])
    with pytest.raises(DataContractError, match="ainda não foi ajustada"):
        policy.recommend({}, ["celular"])

    policy.fit(training_frame)
    with pytest.raises(DataContractError, match="Nenhuma ação elegível"):
        policy.recommend({}, [])


def test_logged_replay_uses_only_matching_historical_actions(training_frame: pd.DataFrame) -> None:
    """Calcula cobertura e recompensa somente onde há feedback factual."""
    policy = BestHistoricalActionPolicy(["celular", "telefone"]).fit(training_frame)
    metrics = evaluate_logged_replay(policy, training_frame)

    assert metrics["accepted_events"] == 5
    assert metrics["conversions"] == 3
    assert metrics["replay_coverage"] == 0.5
    assert metrics["mean_reward"] == 0.6


def test_wilson_interval_is_bounded() -> None:
    """Garante intervalo válido inclusive em casos extremos."""
    lower, upper = wilson_interval(successes=0, observations=10)
    assert 0 <= lower <= upper <= 1
    lower, upper = wilson_interval(successes=10, observations=10)
    assert 0 <= lower <= upper <= 1
