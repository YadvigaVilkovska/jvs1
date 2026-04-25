"""Contract: repository and helper for storing unknown utterances without side effects."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from jeeves_dap.domain.models import UnknownUtterance


class UnknownUtteranceRepository(ABC):
    """Contract: storage abstraction for unknown or unsupported user utterances."""

    @abstractmethod
    def save(self, utterance: UnknownUtterance) -> None:
        """Persist one unknown utterance record."""

    @abstractmethod
    def list_all(self) -> tuple[UnknownUtterance, ...]:
        """Return all stored unknown utterance records."""


class InMemoryUnknownUtteranceRepository(UnknownUtteranceRepository):
    """Contract: minimal PR-3 persistence implementation following the current repository style."""

    def __init__(self) -> None:
        self._utterances: list[UnknownUtterance] = []

    def save(self, utterance: UnknownUtterance) -> None:
        self._utterances.append(utterance)

    def list_all(self) -> tuple[UnknownUtterance, ...]:
        return tuple(self._utterances)


def record_unknown_for_fallback(
    repository: UnknownUtteranceRepository,
    *,
    episode_id: str,
    message_id: str,
    utterance_text: str,
    detected_intent: str | None,
    reason: str,
    fallback_count: int,
    context_snapshot: dict[str, Any] | None = None,
    reviewed: bool = False,
) -> UnknownUtterance:
    """Contract: create and persist one unknown utterance for fallback-only cases."""

    utterance = UnknownUtterance(
        id=str(uuid4()),
        episode_id=episode_id,
        message_id=message_id,
        utterance_text=utterance_text,
        detected_intent=detected_intent,
        reason=reason,
        fallback_count=fallback_count,
        context_snapshot=context_snapshot or {},
        reviewed=reviewed,
        created_at=datetime.now(UTC),
    )
    repository.save(utterance)
    return utterance
