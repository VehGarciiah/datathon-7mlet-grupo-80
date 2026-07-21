"""Testes transacionais do repositório SQLite do serving."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from src.api.repository import (
    ConflictingFeedbackError,
    FeedbackRecord,
    RecommendationRecord,
    SQLiteServingRepository,
)


def _recommendation() -> RecommendationRecord:
    """Cria decisão técnica sem payload pessoal."""
    return RecommendationRecord(
        recommendation_id="recommendation-1",
        created_at=datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc),
        recommended_action="celular",
        policy_id="best_historical_action",
        policy_version="1.0.0",
        policy_mode="approved_fixed_rollback",
        model_version="1.0.0",
        is_exploration=False,
        used_fallback=False,
        reason="Regra fixa de teste.",
        learning_context={"resultado_campanha_anterior": "inexistente"},
        eligible_actions=["celular", "telefone"],
    )


def _feedback(reward: int = 1) -> FeedbackRecord:
    """Cria feedback terminal determinístico."""
    return FeedbackRecord(
        recommendation_id="recommendation-1",
        reward=reward,
        observed_at=datetime(2026, 7, 20, 12, 1, tzinfo=timezone.utc),
        received_at=datetime(2026, 7, 20, 12, 2, tzinfo=timezone.utc),
        learning_applied=False,
        learning_reason="Política fixa não atualiza.",
    )


def test_repository_is_idempotent_under_basic_concurrency(tmp_path) -> None:
    """Insere uma vez mesmo quando oito threads enviam o mesmo feedback."""
    repository = SQLiteServingRepository(tmp_path / "serving.db")
    repository.save_recommendation(_recommendation())

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: repository.save_feedback(_feedback()), range(8)))

    assert sum(inserted for _, inserted in results) == 1
    assert repository.counts() == {
        "recommendations": 1,
        "feedback": 1,
        "observed_reward_total": 1,
        "observed_reward_mean": 1.0,
        "learning_applied": 0,
    }
    assert repository.integrity_check() is True


def test_repository_rejects_conflicting_terminal_feedback(tmp_path) -> None:
    """Não permite alterar recompensa depois do feedback terminal."""
    repository = SQLiteServingRepository(tmp_path / "serving.db")
    repository.save_recommendation(_recommendation())
    repository.save_feedback(_feedback(reward=1))

    with pytest.raises(ConflictingFeedbackError):
        repository.save_feedback(_feedback(reward=0))
