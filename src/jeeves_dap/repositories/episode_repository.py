"""Contract: repository abstractions for episode persistence in the API vertical slice."""

from __future__ import annotations

from abc import ABC, abstractmethod

from jeeves_dap.domain.models import Episode


class EpisodeRepository(ABC):
    """Contract: storage abstraction for reading and writing episodes by id."""

    @abstractmethod
    def save(self, episode: Episode) -> None:
        """Persist one episode snapshot."""

    @abstractmethod
    def get_by_id(self, episode_id: str) -> Episode | None:
        """Return one episode by id when it exists."""


class InMemoryEpisodeRepository(EpisodeRepository):
    """Contract: minimal in-memory episode storage aligned with current repository style."""

    def __init__(self) -> None:
        self._episodes_by_id: dict[str, Episode] = {}

    def save(self, episode: Episode) -> None:
        self._episodes_by_id[episode.id] = episode

    def get_by_id(self, episode_id: str) -> Episode | None:
        return self._episodes_by_id.get(episode_id)
