"""Testes da política Thompson Sampling segmentada."""

from __future__ import annotations

import pandas as pd

from src.features.build_features import ACTION_COLUMN, TARGET_COLUMN
from src.policies.thompson_sampling import SegmentedThompsonSamplingPolicy


def _support_frame() -> pd.DataFrame:
    """Cria dois braços com suporte em um segmento sintético."""
    return pd.DataFrame(
        {
            "segmento": ["a"] * 8,
            ACTION_COLUMN: ["celular"] * 4 + ["telefone"] * 4,
            TARGET_COLUMN: [1, 1, 0, 0, 1, 0, 0, 0],
        }
    )


def _create_policy(seed: int = 42) -> SegmentedThompsonSamplingPolicy:
    """Ajusta suporte sem aquecer o posterior com recompensa histórica."""
    return SegmentedThompsonSamplingPolicy(
        ["celular", "telefone"],
        segment_columns=["segmento"],
        minimum_support_per_action=2,
        random_seed=seed,
    ).fit_support(_support_frame())


def test_policy_explores_then_favors_action_with_better_feedback() -> None:
    """Demonstra exploração inicial e aprendizado após sequência controlada."""
    policy = _create_policy(seed=7)
    context = {"segmento": "a"}
    initial_actions = [
        policy.recommend(context, ["celular", "telefone"]).action for _ in range(100)
    ]
    assert set(initial_actions) == {"celular", "telefone"}

    for index in range(20):
        policy.update("celular", 1, context, feedback_id=f"celular-{index}")
        policy.update("telefone", 0, context, feedback_id=f"telefone-{index}")
    learned_actions = [
        policy.recommend(context, ["celular", "telefone"]).action for _ in range(200)
    ]
    assert learned_actions.count("celular") >= 195


def test_duplicate_feedback_is_not_applied_twice() -> None:
    """Mantém posterior intacto ao receber novamente o mesmo feedback_id."""
    policy = _create_policy()
    context = {"segmento": "a"}
    before = policy.global_posteriors["celular"].alpha

    assert policy.update("celular", 1, context, feedback_id="feedback-1") is True
    assert policy.update("celular", 1, context, feedback_id="feedback-1") is False
    assert policy.global_posteriors["celular"].alpha == before + 1


def test_sparse_segment_uses_global_fallback() -> None:
    """Evita posterior segmentado quando um dos braços não possui suporte mínimo."""
    frame = pd.DataFrame(
        {
            "segmento": ["escasso"] * 5,
            ACTION_COLUMN: ["celular"] * 4 + ["telefone"],
            TARGET_COLUMN: [1, 0, 0, 0, 0],
        }
    )
    policy = SegmentedThompsonSamplingPolicy(
        ["celular", "telefone"],
        segment_columns=["segmento"],
        minimum_support_per_action=2,
    ).fit_support(frame)

    decision = policy.recommend({"segmento": "escasso"}, ["celular", "telefone"])
    assert decision.details["posterior_source"] == "global"
    assert decision.used_fallback is True


def test_atomic_state_round_trip_preserves_next_decision(tmp_path) -> None:
    """Restaura posterior e estado aleatório sem deixar arquivo temporário."""
    policy = _create_policy(seed=99)
    context = {"segmento": "a"}
    policy.update("celular", 1, context, feedback_id="feedback-1")
    state_path = tmp_path / "policy_state.json"
    policy.save_state(state_path)
    restored = SegmentedThompsonSamplingPolicy.load_state(state_path)

    assert restored.to_dict() == policy.to_dict()
    assert restored.recommend(context, ["celular", "telefone"]) == policy.recommend(
        context, ["celular", "telefone"]
    )
    assert not state_path.with_suffix(".json.tmp").exists()
