"""Contract: repository abstractions for pending rule candidate persistence by episode."""

from __future__ import annotations

from abc import ABC, abstractmethod

from jeeves_dap.domain.models import RuleCandidate


class RuleCandidateRepository(ABC):
    """Contract: storage abstraction for one pending rule candidate per episode."""

    @abstractmethod
    def save(self, candidate: RuleCandidate) -> None:
        """Persist one pending rule candidate keyed by episode id."""

    @abstractmethod
    def get_by_episode_id(self, episode_id: str) -> RuleCandidate | None:
        """Return the pending rule candidate for one episode when it exists."""

    @abstractmethod
    def delete_by_episode_id(self, episode_id: str) -> None:
        """Delete the pending rule candidate for one episode."""


class InMemoryRuleCandidateRepository(RuleCandidateRepository):
    """Contract: minimal in-memory pending rule candidate storage."""

    def __init__(self) -> None:
        self._candidates_by_episode_id: dict[str, RuleCandidate] = {}

    def save(self, candidate: RuleCandidate) -> None:
        self._candidates_by_episode_id[candidate.source_episode_id] = candidate

    def get_by_episode_id(self, episode_id: str) -> RuleCandidate | None:
        return self._candidates_by_episode_id.get(episode_id)

    def delete_by_episode_id(self, episode_id: str) -> None:
        self._candidates_by_episode_id.pop(episode_id, None)
