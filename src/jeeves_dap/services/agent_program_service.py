"""Contract: immutable agent program versioning service isolated from the domain layer."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime

from jeeves_dap.domain.agent_program import build_default_agent_program_v1
from jeeves_dap.domain.models import (
    AgentProgram,
    AgentProgramVersion,
    AgentRule,
    QueryProgramContract,
    RuleCandidate,
)
from jeeves_dap.domain.validation import derive_rule_application_mode
from jeeves_dap.repositories.agent_program_repository import AgentProgramVersionRepository


class AgentProgramService:
    """Contract: manage immutable program versions and rule candidate transitions."""

    def __init__(self, repository: AgentProgramVersionRepository) -> None:
        self._repository = repository

    def create_initial_version(self, version_id: str, created_at: datetime) -> AgentProgramVersion:
        """Contract: persist the first program version if storage is empty."""

        existing_versions = self._repository.list_versions()
        if existing_versions:
            return existing_versions[0]

        version = AgentProgramVersion(
            id=version_id,
            version_number=1,
            program=build_default_agent_program_v1(),
            created_at=created_at,
        )
        self._repository.save(version)
        return version

    def create_next_version(
        self,
        version_id: str,
        source_version: AgentProgramVersion,
        *,
        created_at: datetime,
        program_patch: AgentProgram | None = None,
    ) -> AgentProgramVersion:
        """Contract: create a new version without mutating any previously saved snapshot."""

        next_program = deepcopy(program_patch or source_version.program)
        next_version = replace(
            source_version,
            id=version_id,
            version_number=source_version.version_number + 1,
            program=next_program,
            created_at=created_at,
        )
        self._repository.save(next_version)
        return next_version

    def create_rule_candidate(
        self,
        *,
        candidate_id: str,
        source_message_id: str,
        source_episode_id: str,
        text: str,
        key: str | None,
        scope: str,
    ) -> RuleCandidate:
        """Contract: create a pending rule candidate with application mode derived from key."""

        return RuleCandidate(
            id=candidate_id,
            source_message_id=source_message_id,
            source_episode_id=source_episode_id,
            text=text,
            key=key,
            scope=scope,
            application_mode=derive_rule_application_mode(key),
            status="candidate",
            review_state="pending",
            conflict_state="none",
        )

    def confirm_rule_candidate(
        self,
        *,
        active_version: AgentProgramVersion,
        candidate: RuleCandidate,
        new_version_id: str,
        new_rule_id: str,
        created_at: datetime,
    ) -> AgentProgramVersion:
        """Contract: confirm a rule candidate into a new immutable program version."""

        new_rule_status = "active" if candidate.application_mode == "enforced_by_rule_engine" else "future"
        new_rule = AgentRule(
            id=new_rule_id,
            text=candidate.text,
            key=candidate.key,
            scope=candidate.scope,
            status=new_rule_status,
            application_mode=candidate.application_mode,
            source_message_id=candidate.source_message_id,
            source_episode_id=candidate.source_episode_id,
        )

        next_program = deepcopy(active_version.program)
        next_rules = tuple((*next_program.rules, new_rule))

        if candidate.application_mode == "enforced_by_rule_engine":
            next_program = replace(
                next_program,
                rules=next_rules,
                communication_policy=replace(
                    next_program.communication_policy,
                    show_understanding_before_execution=True,
                ),
            )
        else:
            next_program = replace(
                next_program,
                rules=next_rules,
            )

        return self.create_next_version(
            new_version_id,
            active_version,
            created_at=created_at,
            program_patch=next_program,
        )

    def reject_rule_candidate(self, candidate: RuleCandidate) -> RuleCandidate:
        """Contract: reject a pending candidate without mutating any program version."""

        return replace(candidate, review_state="rejected")

    def build_query_program_contract(
        self,
        *,
        active_version: AgentProgramVersion,
        pending_candidates: tuple[RuleCandidate, ...],
    ) -> QueryProgramContract:
        """Contract: build a query contract that separates enforced and future rules."""

        enforced_rules = tuple(
            rule
            for rule in active_version.program.rules
            if rule.application_mode == "enforced_by_rule_engine" and rule.status == "active"
        )
        future_rules = tuple(
            rule
            for rule in active_version.program.rules
            if rule.application_mode == "future_rule" and rule.status == "future"
        )

        return QueryProgramContract(
            active_version=active_version.version_number,
            enforced_rules=enforced_rules,
            future_rules=future_rules,
            pending_candidates=pending_candidates,
            policies={
                "communication_policy": {
                    "show_understanding_before_execution": (
                        active_version.program.communication_policy.show_understanding_before_execution
                    )
                },
                "memory_policy": {
                    "enabled": active_version.program.memory_policy.enabled,
                    "retention": active_version.program.memory_policy.retention,
                },
                "tool_policy": {
                    "allowed_tools": active_version.program.tool_policy.allowed_tools,
                    "require_approval_for_side_effects": (
                        active_version.program.tool_policy.require_approval_for_side_effects
                    ),
                    "side_effects_supported": active_version.program.tool_policy.side_effects_supported,
                },
                "verification_policy": {
                    "must_check_success_condition": (
                        active_version.program.verification_policy.must_check_success_condition
                    ),
                    "default_success_condition_mode": (
                        active_version.program.verification_policy.default_success_condition_mode
                    ),
                },
            },
        )
