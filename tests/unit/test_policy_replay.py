"""Testes das métricas e regras do replay factual."""

from __future__ import annotations

import pandas as pd

from src.evaluation.replay import bootstrap_mean_interval, run_single_replay
from src.features.build_features import ACTION_COLUMN, CONTEXT_COLUMNS, IDENTIFIER_COLUMN, TARGET_COLUMN
from src.policies.thompson_sampling import SegmentedThompsonSamplingPolicy


def _replay_frame() -> pd.DataFrame:
    """Cria eventos completos com contexto mínimo sintético."""
    rows = []
    for index in range(20):
        row = {column: 0 for column in CONTEXT_COLUMNS}
        row["resultado_campanha_anterior"] = "inexistente"
        row[IDENTIFIER_COLUMN] = index + 1
        row[ACTION_COLUMN] = "celular" if index % 2 == 0 else "telefone"
        row[TARGET_COLUMN] = int(row[ACTION_COLUMN] == "celular")
        rows.append(row)
    return pd.DataFrame(rows)


def test_replay_updates_exactly_the_accepted_events() -> None:
    """Não usa recompensas dos eventos cujo canal factual diverge da decisão."""
    frame = _replay_frame()
    policy = SegmentedThompsonSamplingPolicy(
        ["celular", "telefone"],
        segment_columns=["resultado_campanha_anterior", "nunca_contatado_anteriormente"],
        minimum_support_per_action=2,
        random_seed=11,
    ).fit_support(frame)
    summary, trace = run_single_replay(
        policy,
        frame,
        split_name="synthetic",
        action_order=["celular", "telefone"],
        update_policy=True,
        seed=11,
    )

    posterior_updates = sum(
        posterior.alpha + posterior.beta - 2
        for posterior in policy.global_posteriors.values()
    )
    assert posterior_updates == summary["accepted_events"]
    assert trace["observed_reward"].notna().sum() == summary["accepted_events"]
    assert summary["accepted_events"] < summary["total_events"]


def test_bootstrap_interval_is_reproducible_and_bounded() -> None:
    """Produz o mesmo intervalo para a mesma seed e respeita o domínio binário."""
    first = bootstrap_mean_interval(
        [0, 0, 1, 1], iterations=200, confidence_level=0.95, random_seed=3
    )
    second = bootstrap_mean_interval(
        [0, 0, 1, 1], iterations=200, confidence_level=0.95, random_seed=3
    )
    assert first == second
    assert 0 <= first["lower"] <= first["upper"] <= 1
