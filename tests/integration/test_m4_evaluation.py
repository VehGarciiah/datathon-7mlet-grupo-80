"""Teste ponta a ponta da política adaptativa e do replay do M4."""

from __future__ import annotations

import json

import pandas as pd

from src.evaluation.replay import load_replay_config, run_m4_evaluation
from src.policies.thompson_sampling import SegmentedThompsonSamplingPolicy


def test_m4_evaluation_is_reproducible_and_keeps_uncertain_policy_rejected() -> None:
    """Executa 30 seeds, valida artefatos e respeita o gate estatístico."""
    report = run_m4_evaluation("configs/policy.yaml", enable_tracking=False)
    config = load_replay_config("configs/policy.yaml")

    assert report["evaluation_protocol"]["seed_count"] >= 30
    assert report["evaluation_protocol"]["regret"]["value"] is None
    assert report["policy"]["historical_reward_warm_start"] is False
    assert set(report["policy"]["segment_columns"]) == {
        "resultado_campanha_anterior",
        "nunca_contatado_anteriormente",
    }
    assert report["splits"]["test"]["adaptive_policy"]["mean_reward"]["mean"] > 0
    assert report["selection"]["candidate_gate_passed"] is False
    assert report["selection"]["status"] == "rejected"

    saved_report = json.loads(config.evaluation_path.read_text(encoding="utf-8"))
    assert saved_report == report
    seed_results = pd.read_csv(config.seed_results_path)
    assert len(seed_results) == config.seed_count * len(config.evaluation_splits)
    assert set(seed_results["split"]) == {"validation", "test"}
    assert config.comparison_plot_path.stat().st_size > 0

    restored = SegmentedThompsonSamplingPolicy.load_state(config.state_artifact_path)
    assert restored.policy_id == config.policy_id
    assert restored.processed_feedback_ids == set()
