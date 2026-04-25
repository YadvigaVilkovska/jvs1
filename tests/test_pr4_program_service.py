"""Contract: PR-4 regression tests for ProgramService rule candidate behavior."""

from __future__ import annotations

from datetime import UTC, datetime

from jeeves_dap.repositories.agent_program_repository import InMemoryAgentProgramVersionRepository
from jeeves_dap.services.agent_program_service import AgentProgramService


def test_create_enforceable_rule_candidate() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())

    candidate = service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m1",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )

    assert candidate.application_mode == "enforced_by_rule_engine"
    assert candidate.status == "candidate"
    assert candidate.review_state == "pending"
    assert candidate.conflict_state == "none"


def test_create_future_rule_candidate_for_unknown_key() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())

    candidate = service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m1",
        source_episode_id="e1",
        text="Всегда добавляй список багов",
        key="always_add_bug_list",
        scope="code_review",
    )

    assert candidate.application_mode == "future_rule"
    assert candidate.status == "candidate"


def test_confirm_enforceable_rule_creates_new_version() -> None:
    repository = InMemoryAgentProgramVersionRepository()
    service = AgentProgramService(repository)
    active_version = service.create_initial_version("v1", datetime.now(UTC))
    candidate = service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m1",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )

    next_version = service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )

    assert next_version.version_number == 2
    assert len(next_version.program.rules) == 1
    assert next_version.program.rules[0].status == "active"


def test_confirm_enforceable_rule_patches_communication_policy() -> None:
    repository = InMemoryAgentProgramVersionRepository()
    service = AgentProgramService(repository)
    active_version = service.create_initial_version("v1", datetime.now(UTC))
    candidate = service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m1",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )

    next_version = service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )

    assert next_version.program.communication_policy.show_understanding_before_execution is True


def test_confirm_future_rule_creates_new_version_without_policy_patch() -> None:
    repository = InMemoryAgentProgramVersionRepository()
    service = AgentProgramService(repository)
    active_version = service.create_initial_version("v1", datetime.now(UTC))
    candidate = service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m1",
        source_episode_id="e1",
        text="Всегда добавляй список багов",
        key="always_add_bug_list",
        scope="code_review",
    )

    next_version = service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )

    assert next_version.version_number == 2
    assert next_version.program.rules[0].status == "future"
    assert next_version.program.communication_policy.show_understanding_before_execution is False


def test_reject_rule_candidate_does_not_create_version() -> None:
    repository = InMemoryAgentProgramVersionRepository()
    service = AgentProgramService(repository)
    service.create_initial_version("v1", datetime.now(UTC))
    candidate = service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m1",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )

    rejected = service.reject_rule_candidate(candidate)

    assert rejected.review_state == "rejected"
    assert len(repository.list_versions()) == 1


def test_previous_program_version_not_mutated_after_confirm() -> None:
    repository = InMemoryAgentProgramVersionRepository()
    service = AgentProgramService(repository)
    active_version = service.create_initial_version("v1", datetime.now(UTC))
    candidate = service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m1",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )

    service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )

    assert active_version.version_number == 1
    assert active_version.program.rules == ()
    assert active_version.program.communication_policy.show_understanding_before_execution is False


def test_query_program_contract_splits_enforced_and_future_rules() -> None:
    repository = InMemoryAgentProgramVersionRepository()
    service = AgentProgramService(repository)
    v1 = service.create_initial_version("v1", datetime.now(UTC))
    enforceable_candidate = service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m1",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    v2 = service.confirm_rule_candidate(
        active_version=v1,
        candidate=enforceable_candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )
    future_candidate = service.create_rule_candidate(
        candidate_id="c2",
        source_message_id="m2",
        source_episode_id="e1",
        text="Всегда добавляй список багов",
        key="always_add_bug_list",
        scope="code_review",
    )
    v3 = service.confirm_rule_candidate(
        active_version=v2,
        candidate=future_candidate,
        new_version_id="v3",
        new_rule_id="r2",
        created_at=datetime.now(UTC),
    )
    pending_candidate = service.create_rule_candidate(
        candidate_id="c3",
        source_message_id="m3",
        source_episode_id="e1",
        text="Ещё одно правило",
        key=None,
        scope="all_tasks",
    )

    contract = service.build_query_program_contract(
        active_version=v3,
        pending_candidates=(pending_candidate,),
    )

    assert len(contract.enforced_rules) == 1
    assert contract.enforced_rules[0].application_mode == "enforced_by_rule_engine"
    assert len(contract.future_rules) == 1
    assert contract.future_rules[0].application_mode == "future_rule"
    assert contract.pending_candidates == (pending_candidate,)


def test_query_program_contract_includes_policies() -> None:
    repository = InMemoryAgentProgramVersionRepository()
    service = AgentProgramService(repository)
    active_version = service.create_initial_version("v1", datetime.now(UTC))

    contract = service.build_query_program_contract(
        active_version=active_version,
        pending_candidates=(),
    )

    assert "communication_policy" in contract.policies
    assert "memory_policy" in contract.policies
    assert "tool_policy" in contract.policies
    assert "verification_policy" in contract.policies


def test_must_check_success_condition_candidate_is_future_rule() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())

    candidate = service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m1",
        source_episode_id="e1",
        text="Проверяй условие успеха",
        key="must_check_success_condition",
        scope="all_tasks",
    )

    assert candidate.application_mode == "future_rule"
