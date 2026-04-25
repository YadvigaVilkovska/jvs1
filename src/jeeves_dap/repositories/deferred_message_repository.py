"""Contract: repository for storing one deferred message per episode during pending switch flow."""

from __future__ import annotations

from abc import ABC, abstractmethod

from jeeves_dap.domain.models import DeferredMessage


class DeferredMessageRepository(ABC):
    """Contract: storage abstraction for deferred messages tied to one episode."""

    @abstractmethod
    def save(self, deferred: DeferredMessage) -> None:
        """Persist the deferred message for one episode."""

    @abstractmethod
    def get_by_episode_id(self, episode_id: str) -> DeferredMessage | None:
        """Return deferred message by episode id when it exists."""

    @abstractmethod
    def delete_by_episode_id(self, episode_id: str) -> None:
        """Delete the deferred message for one episode."""


class InMemoryDeferredMessageRepository(DeferredMessageRepository):
    """Contract: minimal in-memory deferred storage matching current repository style."""

    def __init__(self) -> None:
        self._deferred_by_episode_id: dict[str, DeferredMessage] = {}

    def save(self, deferred: DeferredMessage) -> None:
        self._deferred_by_episode_id[deferred.episode_id] = deferred

    def get_by_episode_id(self, episode_id: str) -> DeferredMessage | None:
        return self._deferred_by_episode_id.get(episode_id)

    def delete_by_episode_id(self, episode_id: str) -> None:
        self._deferred_by_episode_id.pop(episode_id, None)
