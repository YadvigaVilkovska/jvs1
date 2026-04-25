"""Contract: PR-3 regression tests for mandatory fields, review flags, and unknown utterances."""

from __future__ import annotations

from jeeves_dap.domain.models import IntakeResult, MessageItem
from jeeves_dap.domain.validation import (
    compute_understanding_sufficiency,
    derive_rule_application_mode,
    derive_review_flags,
    validate_item,
)
from jeeves_dap.repositories.unknown_utterance_repository import (
    InMemoryUnknownUtteranceRepository,
    record_unknown_for_fallback,
)


def test_task_requires_non_empty_task_item() -> None:
    item = MessageItem(type="task", text="   ")

    validation = validate_item(item)

    assert validation.is_valid is False
    assert validation.reason == "empty_text"


def test_rule_update_requires_non_empty_rule_candidate() -> None:
    item = MessageItem(type="rule_candidate", text="   ", scope="all_tasks")

    validation = validate_item(item)

    assert validation.is_valid is False
    assert validation.reason == "empty_text"


def test_rule_candidate_requires_scope() -> None:
    item = MessageItem(type="rule_candidate", text="Показывай понимание", scope=None)

    validation = validate_item(item)

    assert validation.is_valid is False
    assert validation.reason == "missing_scope"


def test_correction_requires_non_empty_correction_item() -> None:
    item = MessageItem(type="correction", text=" ")

    validation = validate_item(item)

    assert validation.is_valid is False
    assert validation.reason == "empty_text"


def test_feedback_requires_non_empty_feedback_item() -> None:
    item = MessageItem(type="feedback", text="")

    validation = validate_item(item)

    assert validation.is_valid is False
    assert validation.reason == "empty_text"


def test_query_is_sufficient_without_items() -> None:
    intake = IntakeResult(message_id="m1", primary_intent="query", items=())

    assert compute_understanding_sufficiency(intake) is True


def test_cancel_is_sufficient_without_items() -> None:
    intake = IntakeResult(message_id="m1", primary_intent="cancel", items=())

    assert compute_understanding_sufficiency(intake) is True


def test_chat_is_sufficient_without_items() -> None:
    intake = IntakeResult(message_id="m1", primary_intent="chat", items=())

    assert compute_understanding_sufficiency(intake) is True


def test_chat_with_ambiguous_request_needs_clarification() -> None:
    intake = IntakeResult(
        message_id="m1",
        primary_intent="chat",
        items=(MessageItem(type="ambiguous_request", text="Сделай что-нибудь полезное"),),
    )

    flags = derive_review_flags(intake)

    assert flags.needs_clarification is True
    assert flags.requires_user_review is False


def test_ambiguous_request_must_not_execute() -> None:
    intake = IntakeResult(
        message_id="m1",
        primary_intent="chat",
        items=(MessageItem(type="ambiguous_request", text="Сделай что-нибудь хорошее"),),
    )

    assert compute_understanding_sufficiency(intake) is False


def test_known_rule_key_sets_enforced_application_mode() -> None:
    item = MessageItem(
        type="rule_candidate",
        text="Показывай понимание",
        scope="all_tasks",
        key="show_understanding_before_execution",
    )

    validation = validate_item(item)

    assert validation.normalized_item.application_mode == "enforced_by_rule_engine"


def test_unknown_rule_key_sets_future_rule() -> None:
    assert derive_rule_application_mode("some_unknown_rule") == "future_rule"


def test_must_check_success_condition_sets_future_rule() -> None:
    assert derive_rule_application_mode("must_check_success_condition") == "future_rule"


def test_missing_mandatory_fields_records_unknown_utterance() -> None:
    repository = InMemoryUnknownUtteranceRepository()

    record = record_unknown_for_fallback(
        repository,
        episode_id="e1",
        message_id="m1",
        utterance_text="Сделай",
        detected_intent="task",
        reason="missing_mandatory_fields",
        fallback_count=1,
        context_snapshot={"state": "open"},
    )

    assert repository.list_all() == (record,)
    assert record.reason == "missing_mandatory_fields"


def test_invalid_schema_reason_can_be_recorded_as_unknown_utterance() -> None:
    repository = InMemoryUnknownUtteranceRepository()

    record = record_unknown_for_fallback(
        repository,
        episode_id="e1",
        message_id="m1",
        utterance_text="{bad json",
        detected_intent=None,
        reason="invalid_schema_after_retries",
        fallback_count=2,
        context_snapshot={"attempt": 3},
    )

    assert repository.list_all() == (record,)
    assert record.reason == "invalid_schema_after_retries"
    assert record.context_snapshot == {"attempt": 3}


def test_derive_review_flags_decision_table() -> None:
    valid_chat = derive_review_flags(
        IntakeResult(message_id="m1", primary_intent="chat", items=())
    )
    ambiguous_chat = derive_review_flags(
        IntakeResult(
            message_id="m2",
            primary_intent="chat",
            items=(MessageItem(type="ambiguous_request", text="Сделай что-нибудь"),),
        )
    )
    valid_query = derive_review_flags(
        IntakeResult(message_id="m3", primary_intent="query", items=())
    )
    valid_feedback = derive_review_flags(
        IntakeResult(
            message_id="m4",
            primary_intent="feedback",
            items=(MessageItem(type="feedback", text="Хорошо"),),
        )
    )
    valid_cancel = derive_review_flags(
        IntakeResult(message_id="m5", primary_intent="cancel", items=())
    )
    valid_task_without_rule = derive_review_flags(
        IntakeResult(
            message_id="m6",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    valid_task_with_rule = derive_review_flags(
        IntakeResult(
            message_id="m7",
            primary_intent="task",
            items=(
                MessageItem(type="task", text="Проверить код"),
                MessageItem(
                    type="rule_candidate",
                    text="Показывай понимание",
                    scope="all_tasks",
                    key="show_understanding_before_execution",
                ),
            ),
        )
    )
    rule_update_enforceable = derive_review_flags(
        IntakeResult(
            message_id="m8",
            primary_intent="rule_update",
            items=(
                MessageItem(
                    type="rule_candidate",
                    text="Показывай понимание",
                    scope="all_tasks",
                    key="show_understanding_before_execution",
                ),
            ),
        )
    )
    rule_update_future = derive_review_flags(
        IntakeResult(
            message_id="m9",
            primary_intent="rule_update",
            items=(
                MessageItem(
                    type="rule_candidate",
                    text="Всегда добавляй баги",
                    scope="code_review",
                    key="always_add_bug_list",
                ),
            ),
        )
    )
    missing_task_fields = derive_review_flags(
        IntakeResult(
            message_id="m10",
            primary_intent="task",
            items=(MessageItem(type="query", text="Что активно?"),),
        )
    )
    invalid_feedback = derive_review_flags(
        IntakeResult(
            message_id="m11",
            primary_intent="feedback",
            items=(MessageItem(type="feedback", text=""),),
        )
    )

    assert (valid_chat.needs_clarification, valid_chat.requires_user_review) == (False, False)
    assert (ambiguous_chat.needs_clarification, ambiguous_chat.requires_user_review) == (True, False)
    assert (valid_query.needs_clarification, valid_query.requires_user_review) == (False, False)
    assert (valid_feedback.needs_clarification, valid_feedback.requires_user_review) == (False, False)
    assert (valid_cancel.needs_clarification, valid_cancel.requires_user_review) == (False, False)
    assert (
        valid_task_without_rule.needs_clarification,
        valid_task_without_rule.requires_user_review,
    ) == (False, False)
    assert (valid_task_with_rule.needs_clarification, valid_task_with_rule.requires_user_review) == (False, True)
    assert (
        rule_update_enforceable.needs_clarification,
        rule_update_enforceable.requires_user_review,
    ) == (False, True)
    assert (rule_update_future.needs_clarification, rule_update_future.requires_user_review) == (False, True)
    assert (
        missing_task_fields.needs_clarification,
        missing_task_fields.requires_user_review,
    ) == (True, False)
    assert (invalid_feedback.needs_clarification, invalid_feedback.requires_user_review) == (True, False)


def test_needs_clarification_suppresses_user_review() -> None:
    intake = IntakeResult(
        message_id="m1",
        primary_intent="task",
        items=(
            MessageItem(type="ambiguous_request", text="Сделай что-нибудь"),
            MessageItem(
                type="rule_candidate",
                text="Показывай понимание",
                scope="all_tasks",
                key="show_understanding_before_execution",
            ),
        ),
    )

    flags = derive_review_flags(intake)

    assert flags.needs_clarification is True
    assert flags.requires_user_review is False
