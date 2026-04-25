"""Contract: PR-1 regression tests for Jeeves DAP data foundation and contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import get_args

from jeeves_dap.domain.agent_program import (
    KNOWN_RULE_KEYS,
    build_default_agent_program_v1,
)
from jeeves_dap.domain.models import (
    ApplicationMode,
    DeferredMessage,
    IntakeResult,
    MessageItem,
    MessageItemType,
    PrimaryIntent,
    QueryProgramContract,
    UnknownUtterance,
)
from jeeves_dap.domain.validation import (
    compute_understanding_sufficiency,
    derive_review_flags,
    validate_item,
)
from jeeves_dap.repositories.agent_program_repository import InMemoryAgentProgramVersionRepository
from jeeves_dap.services.agent_program_service import AgentProgramService


def test_domain_agent_program_does_not_import_repository() -> None:
    with open("src/jeeves_dap/domain/agent_program.py", encoding="utf-8") as file:
        source = file.read()

    assert "jeeves_dap.repositories" not in source


def test_no_mixed_intent_enum() -> None:
    assert set(get_args(PrimaryIntent)) == {
        "task",
        "rule_update",
        "correction",
        "feedback",
        "query",
        "cancel",
        "chat",
    }
    assert "mixed" not in get_args(PrimaryIntent)


def test_default_agent_program_v1() -> None:
    program = build_default_agent_program_v1()

    assert program.communication_policy.show_understanding_before_execution is False
    assert program.memory_policy.enabled is False
    assert program.memory_policy.retention == "episode"
    assert program.tool_policy.allowed_tools == ()
    assert program.tool_policy.require_approval_for_side_effects is False
    assert program.tool_policy.side_effects_supported is False
    assert program.verification_policy.must_check_success_condition is True
    assert (
        program.verification_policy.default_success_condition_mode
        == "completed_status_is_success"
    )


def test_program_version_is_immutable() -> None:
    repository = InMemoryAgentProgramVersionRepository()
    service = AgentProgramService(repository)
    created_at = datetime.now(UTC)

    v1 = service.create_initial_version("v1", created_at)
    patched_program = replace(
        v1.program,
        communication_policy=replace(
            v1.program.communication_policy,
            show_understanding_before_execution=True,
        ),
    )
    v2 = service.create_next_version(
        "v2",
        v1,
        created_at=datetime.now(UTC),
        program_patch=patched_program,
    )

    persisted_v1 = repository.get_by_version_number(1)
    persisted_v2 = repository.get_by_version_number(2)

    assert persisted_v1 is not None
    assert persisted_v2 is not None
    assert persisted_v1.program.communication_policy.show_understanding_before_execution is False
    assert persisted_v2.program.communication_policy.show_understanding_before_execution is True
    assert persisted_v1.program != persisted_v2.program


def test_known_rule_keys_only_show_understanding() -> None:
    assert KNOWN_RULE_KEYS == frozenset({"show_understanding_before_execution"})


def test_must_check_success_condition_is_not_rule_key() -> None:
    assert "must_check_success_condition" not in KNOWN_RULE_KEYS


def test_unknown_rule_becomes_future_rule() -> None:
    item = MessageItem(
        type="rule_candidate",
        text="Всегда добавляй список багов.",
        scope="code_review",
        key="add_bug_list",
    )

    validation = validate_item(item)

    assert validation.is_valid is True
    assert validation.normalized_item.application_mode == "future_rule"


def test_message_item_vocabulary_is_mvp_only() -> None:
    assert set(get_args(MessageItemType)) == {
        "task",
        "rule_candidate",
        "correction",
        "feedback",
        "query",
        "cancel",
        "ambiguous_request",
    }

    assert set(get_args(ApplicationMode)) == {
        "enforced_by_rule_engine",
        "future_rule",
    }


def test_compute_understanding_sufficiency_task_requires_task_item() -> None:
    intake_without_task = IntakeResult(
        message_id="m1",
        primary_intent="task",
        items=(MessageItem(type="query", text="Какие правила?"),),
    )
    intake_with_task = IntakeResult(
        message_id="m2",
        primary_intent="task",
        items=(MessageItem(type="task", text="Проверить код"),),
    )

    assert compute_understanding_sufficiency(intake_without_task) is False
    assert compute_understanding_sufficiency(intake_with_task) is True


def test_ambiguous_request_needs_clarification() -> None:
    intake = IntakeResult(
        message_id="m1",
        primary_intent="chat",
        items=(MessageItem(type="ambiguous_request", text="Сделай что-нибудь хорошее"),),
    )

    flags = derive_review_flags(intake)

    assert flags.needs_clarification is True
    assert flags.requires_user_review is False


def test_query_contract_has_enforced_and_future_rules_slots() -> None:
    contract = QueryProgramContract(active_version=1)

    assert hasattr(contract, "enforced_rules")
    assert hasattr(contract, "future_rules")
    assert contract.enforced_rules == ()
    assert contract.future_rules == ()


def test_unknown_utterance_model_can_store_reason_and_context() -> None:
    utterance = UnknownUtterance(
        id="u1",
        episode_id="e1",
        message_id="m1",
        utterance_text="???",
        detected_intent=None,
        reason="ambiguous_request",
        context_snapshot={"state": "open"},
    )

    assert utterance.reason == "ambiguous_request"
    assert utterance.context_snapshot == {"state": "open"}


def test_deferred_message_model_exists() -> None:
    intake = IntakeResult(
        message_id="m1",
        primary_intent="query",
        items=(MessageItem(type="query", text="Какие правила активны?"),),
    )

    deferred = DeferredMessage(
        id="d1",
        episode_id="e1",
        message_id="m1",
        intake_result=intake,
        created_at=datetime.now(UTC),
    )

    assert deferred.intake_result.message_id == "m1"
    assert deferred.episode_id == "e1"
