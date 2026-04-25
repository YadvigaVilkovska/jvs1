"""Contract: repository abstractions for pending task understanding persistence by episode."""

from __future__ import annotations

from abc import ABC, abstractmethod

from jeeves_dap.domain.models import PendingUnderstanding


class PendingUnderstandingRepository(ABC):
    """Contract: storage abstraction for one pending task understanding per episode."""

    @abstractmethod
    def save(self, pending: PendingUnderstanding) -> None:
        """Persist one pending understanding keyed by episode id."""

    @abstractmethod
    def get_by_episode_id(self, episode_id: str) -> PendingUnderstanding | None:
        """Return the pending understanding for one episode when it exists."""

    @abstractmethod
    def delete_by_episode_id(self, episode_id: str) -> None:
        """Delete the pending understanding for one episode."""


class InMemoryPendingUnderstandingRepository(PendingUnderstandingRepository):
    """Contract: minimal in-memory pending understanding storage."""

    def __init__(self) -> None:
        self._pending_by_episode_id: dict[str, PendingUnderstanding] = {}

    def save(self, pending: PendingUnderstanding) -> None:
        self._pending_by_episode_id[pending.episode_id] = pending

    def get_by_episode_id(self, episode_id: str) -> PendingUnderstanding | None:
        return self._pending_by_episode_id.get(episode_id)

    def delete_by_episode_id(self, episode_id: str) -> None:
        self._pending_by_episode_id.pop(episode_id, None)
