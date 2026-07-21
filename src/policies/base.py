"""Contrato comum para políticas determinísticas e adaptativas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Decision:
    """Representa uma ação selecionada de forma auditável."""

    action: str
    policy_id: str
    policy_version: str
    is_exploration: bool
    used_fallback: bool
    reason: str
    details: dict[str, Any] | None = None


class Policy(Protocol):
    """Define a interface que será compartilhada com políticas adaptativas."""

    def recommend(self, context: dict, eligible_actions: list[str]) -> Decision:
        """Seleciona uma ação elegível sem executar a ação no mundo externo."""
        ...

    def update(
        self,
        action: str,
        reward: int,
        context: dict,
        *,
        feedback_id: str | None = None,
    ) -> bool:
        """Atualiza somente o braço observado e rejeita feedback duplicado."""
        ...
