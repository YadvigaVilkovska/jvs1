"""Contract: minimal repository for immutable agent program version persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod

from jeeves_dap.domain.models import AgentProgramVersion


class AgentProgramVersionRepository(ABC):
    """Contract: storage abstraction for writing and reading program versions."""

    @abstractmethod
    def save(self, version: AgentProgramVersion) -> None:
        """Persist one version snapshot."""

    @abstractmethod
    def get_by_version_number(self, version_number: int) -> AgentProgramVersion | None:
        """Return one stored version by number."""

    @abstractmethod
    def list_versions(self) -> tuple[AgentProgramVersion, ...]:
        """Return all stored versions in ascending version order."""


class InMemoryAgentProgramVersionRepository(AgentProgramVersionRepository):
    """Contract: PR-1 storage implementation for a repository with no existing persistence layer yet."""

    def __init__(self) -> None:
        self._versions: dict[int, AgentProgramVersion] = {}

    def save(self, version: AgentProgramVersion) -> None:
        self._versions[version.version_number] = version

    def get_by_version_number(self, version_number: int) -> AgentProgramVersion | None:
        return self._versions.get(version_number)

    def list_versions(self) -> tuple[AgentProgramVersion, ...]:
        return tuple(self._versions[number] for number in sorted(self._versions))
