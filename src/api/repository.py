"""Repositório SQLite transacional para decisões e feedback."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


class RecommendationNotFoundError(LookupError):
    """Indica feedback sem recomendação registrada."""


class ConflictingFeedbackError(RuntimeError):
    """Indica segunda recompensa divergente para a mesma decisão."""


@dataclass(frozen=True)
class RecommendationRecord:
    """Estado mínimo necessário para auditoria e atualização da política."""

    recommendation_id: str
    created_at: datetime
    recommended_action: str
    policy_id: str
    policy_version: str
    policy_mode: str
    model_version: str
    is_exploration: bool
    used_fallback: bool
    reason: str
    learning_context: dict[str, Any]
    eligible_actions: list[str]


@dataclass(frozen=True)
class FeedbackRecord:
    """Representa feedback terminal persistido uma única vez."""

    recommendation_id: str
    reward: int
    observed_at: datetime
    received_at: datetime
    learning_applied: bool
    learning_reason: str


class SQLiteServingRepository:
    """Mantém idempotência por chave única e transações `BEGIN IMMEDIATE`."""

    def __init__(self, database_path: str | Path, *, timeout_seconds: float = 10) -> None:
        self.database_path = Path(database_path)
        self.timeout_seconds = timeout_seconds
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        """Abre conexão curta e habilita integridade relacional."""
        connection = sqlite3.connect(
            self.database_path,
            timeout=self.timeout_seconds,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def _connection(self):  # type: ignore[no-untyped-def]
        """Fecha explicitamente a conexão, inclusive no Windows."""
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        """Cria schema idempotente e ativa WAL para leitura concorrente."""
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS recommendations (
                    recommendation_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    recommended_action TEXT NOT NULL,
                    policy_id TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    policy_mode TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    is_exploration INTEGER NOT NULL CHECK (is_exploration IN (0, 1)),
                    used_fallback INTEGER NOT NULL CHECK (used_fallback IN (0, 1)),
                    reason TEXT NOT NULL,
                    learning_context_json TEXT NOT NULL,
                    eligible_actions_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    recommendation_id TEXT PRIMARY KEY,
                    reward INTEGER NOT NULL CHECK (reward IN (0, 1)),
                    observed_at TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    learning_applied INTEGER NOT NULL CHECK (learning_applied IN (0, 1)),
                    learning_reason TEXT NOT NULL,
                    FOREIGN KEY (recommendation_id)
                        REFERENCES recommendations(recommendation_id)
                        ON DELETE RESTRICT
                );
                """
            )

    def save_recommendation(self, record: RecommendationRecord) -> None:
        """Registra decisão sem armazenar o payload completo do cliente."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO recommendations (
                    recommendation_id, created_at, recommended_action,
                    policy_id, policy_version, policy_mode, model_version,
                    is_exploration, used_fallback, reason,
                    learning_context_json, eligible_actions_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.recommendation_id,
                    record.created_at.isoformat(),
                    record.recommended_action,
                    record.policy_id,
                    record.policy_version,
                    record.policy_mode,
                    record.model_version,
                    int(record.is_exploration),
                    int(record.used_fallback),
                    record.reason,
                    json.dumps(record.learning_context, ensure_ascii=False, sort_keys=True),
                    json.dumps(record.eligible_actions, ensure_ascii=False),
                ),
            )
            connection.commit()

    def get_recommendation(self, recommendation_id: str) -> RecommendationRecord | None:
        """Recupera somente o contexto mínimo ligado à decisão."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM recommendations WHERE recommendation_id = ?",
                (recommendation_id,),
            ).fetchone()
        if row is None:
            return None
        return RecommendationRecord(
            recommendation_id=row["recommendation_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            recommended_action=row["recommended_action"],
            policy_id=row["policy_id"],
            policy_version=row["policy_version"],
            policy_mode=row["policy_mode"],
            model_version=row["model_version"],
            is_exploration=bool(row["is_exploration"]),
            used_fallback=bool(row["used_fallback"]),
            reason=row["reason"],
            learning_context=json.loads(row["learning_context_json"]),
            eligible_actions=json.loads(row["eligible_actions_json"]),
        )

    def get_feedback(self, recommendation_id: str) -> FeedbackRecord | None:
        """Consulta feedback terminal previamente persistido."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM feedback WHERE recommendation_id = ?",
                (recommendation_id,),
            ).fetchone()
        if row is None:
            return None
        return FeedbackRecord(
            recommendation_id=row["recommendation_id"],
            reward=int(row["reward"]),
            observed_at=datetime.fromisoformat(row["observed_at"]),
            received_at=datetime.fromisoformat(row["received_at"]),
            learning_applied=bool(row["learning_applied"]),
            learning_reason=row["learning_reason"],
        )

    def save_feedback(self, feedback: FeedbackRecord) -> tuple[FeedbackRecord, bool]:
        """Insere feedback uma vez; repetição idêntica retorna o registro existente."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            recommendation = connection.execute(
                "SELECT 1 FROM recommendations WHERE recommendation_id = ?",
                (feedback.recommendation_id,),
            ).fetchone()
            if recommendation is None:
                connection.rollback()
                raise RecommendationNotFoundError(feedback.recommendation_id)

            existing_row = connection.execute(
                "SELECT * FROM feedback WHERE recommendation_id = ?",
                (feedback.recommendation_id,),
            ).fetchone()
            if existing_row is not None:
                connection.rollback()
                existing = FeedbackRecord(
                    recommendation_id=existing_row["recommendation_id"],
                    reward=int(existing_row["reward"]),
                    observed_at=datetime.fromisoformat(existing_row["observed_at"]),
                    received_at=datetime.fromisoformat(existing_row["received_at"]),
                    learning_applied=bool(existing_row["learning_applied"]),
                    learning_reason=existing_row["learning_reason"],
                )
                if (
                    existing.reward != feedback.reward
                    or existing.observed_at != feedback.observed_at
                ):
                    raise ConflictingFeedbackError(feedback.recommendation_id)
                return existing, False

            connection.execute(
                """
                INSERT INTO feedback (
                    recommendation_id, reward, observed_at, received_at,
                    learning_applied, learning_reason
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback.recommendation_id,
                    feedback.reward,
                    feedback.observed_at.isoformat(),
                    feedback.received_at.isoformat(),
                    int(feedback.learning_applied),
                    feedback.learning_reason,
                ),
            )
            connection.commit()
        return feedback, True

    def counts(self) -> dict[str, int | float]:
        """Expõe apenas volumes agregados para observabilidade."""
        with self._connection() as connection:
            recommendation_count = connection.execute(
                "SELECT COUNT(*) FROM recommendations"
            ).fetchone()[0]
            feedback_count = connection.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
            reward_sum = connection.execute(
                "SELECT COALESCE(SUM(reward), 0) FROM feedback"
            ).fetchone()[0]
            learning_count = connection.execute(
                "SELECT COUNT(*) FROM feedback WHERE learning_applied = 1"
            ).fetchone()[0]
        return {
            "recommendations": int(recommendation_count),
            "feedback": int(feedback_count),
            "observed_reward_total": int(reward_sum),
            "observed_reward_mean": (float(reward_sum / feedback_count) if feedback_count else 0.0),
            "learning_applied": int(learning_count),
        }

    def integrity_check(self) -> bool:
        """Verifica rapidamente corrupção do arquivo SQLite."""
        with self._connection() as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        return result == "ok"
