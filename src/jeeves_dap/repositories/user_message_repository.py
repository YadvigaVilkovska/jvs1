"""Contract: repository abstractions for user message persistence in the API vertical slice."""

from __future__ import annotations

from abc import ABC, abstractmethod

from jeeves_dap.domain.models import UserMessage


class UserMessageRepository(ABC):
    """Contract: storage abstraction for writing and listing user messages."""

    @abstractmethod
    def save(self, message: UserMessage) -> None:
        """Persist one user message."""

    @abstractmethod
    def list_by_episode_id(self, episode_id: str) -> tuple[UserMessage, ...]:
        """Return messages stored for one episode in insertion order."""


class InMemoryUserMessageRepository(UserMessageRepository):
    """Contract: minimal in-memory user message storage for API request history."""

    def __init__(self) -> None:
        self._messages_by_episode_id: dict[str, list[UserMessage]] = {}

    def save(self, message: UserMessage) -> None:
        self._messages_by_episode_id.setdefault(message.episode_id, []).append(message)

    def list_by_episode_id(self, episode_id: str) -> tuple[UserMessage, ...]:
        return tuple(self._messages_by_episode_id.get(episode_id, []))
