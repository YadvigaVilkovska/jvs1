"""Contract: PR-2 regression tests for deterministic command handling and classifier seams."""

from __future__ import annotations

from abc import ABC
from typing import get_type_hints

from jeeves_dap.domain.models import IntakeResult, MessageItem
from jeeves_dap.services.classification import DevCommandClassifier, IntentClassifier, StubClassifier
from jeeves_dap.services.deterministic_preprocessor import (
    CANCEL_COMMANDS,
    CONFIRM_COMMANDS,
    REJECT_COMMANDS,
    DeterministicPreProcessor,
)


def test_preprocessor_confirm_in_pending_state() -> None:
    preprocessor = DeterministicPreProcessor()

    result = preprocessor.preprocess("да", "pending_rule_review")

    assert result is not None
    assert result.action == "confirm"


def test_preprocessor_reject_in_pending_state() -> None:
    preprocessor = DeterministicPreProcessor()

    result = preprocessor.preprocess("не сохраняй", "pending_switch_confirmation")

    assert result is not None
    assert result.action == "reject"


def test_preprocessor_cancel_in_any_state() -> None:
    preprocessor = DeterministicPreProcessor()

    result = preprocessor.preprocess("отмена", "open")

    assert result is not None
    assert result.action == "cancel"


def test_preprocessor_no_confirm_in_open_state() -> None:
    preprocessor = DeterministicPreProcessor()

    result = preprocessor.preprocess("да", "open")

    assert result is None


def test_preprocessor_exact_match_only() -> None:
    preprocessor = DeterministicPreProcessor()

    result = preprocessor.preprocess("не   так", "pending_understanding_review")

    assert result is not None
    assert result.action == "reject"
    assert result.normalized_text == "не так"


def test_preprocessor_no_substring_false_positive() -> None:
    preprocessor = DeterministicPreProcessor()

    result = preprocessor.preprocess(
        "Так, подожди, нет, дай подумать.",
        "pending_rule_review",
    )

    assert result is None


def test_preprocessor_da_no_with_punctuation() -> None:
    preprocessor = DeterministicPreProcessor()

    confirm_result = preprocessor.preprocess("  Да. ", "pending_understanding_review")
    reject_result = preprocessor.preprocess("Нет.", "pending_understanding_review")

    assert confirm_result is not None
    assert confirm_result.action == "confirm"
    assert reject_result is not None
    assert reject_result.action == "reject"


def test_preprocessor_real_utf8_da() -> None:
    preprocessor = DeterministicPreProcessor()

    result = preprocessor.preprocess("да", "pending_understanding_review")

    assert result is not None
    assert result.action == "confirm"
    assert result.normalized_text == "да"


def test_preprocessor_real_utf8_net() -> None:
    preprocessor = DeterministicPreProcessor()

    result = preprocessor.preprocess("нет", "pending_rule_review")

    assert result is not None
    assert result.action == "reject"
    assert result.normalized_text == "нет"


def test_preprocessor_real_utf8_otmena() -> None:
    preprocessor = DeterministicPreProcessor()

    result = preprocessor.preprocess("отмена", "completed")

    assert result is not None
    assert result.action == "cancel"
    assert result.normalized_text == "отмена"


def test_command_sets_contain_real_utf8_strings() -> None:
    assert "да" in CONFIRM_COMMANDS
    assert "нет" in REJECT_COMMANDS
    assert "отмена" in CANCEL_COMMANDS
    assert "начнём заново" in CANCEL_COMMANDS


def test_command_sets_do_not_contain_mojibake_dash_sequences() -> None:
    all_commands = CONFIRM_COMMANDS | REJECT_COMMANDS | CANCEL_COMMANDS

    assert all("–" not in command for command in all_commands)
    assert all("â" not in command for command in all_commands)
    assert all("ã" not in command for command in all_commands)


def test_intent_classifier_interface_exists() -> None:
    assert issubclass(IntentClassifier, ABC)
    assert callable(IntentClassifier.classify)
    assert "text" in get_type_hints(IntentClassifier.classify)


def test_stub_classifier_returns_configured_result() -> None:
    intake = IntakeResult(
        message_id="m1",
        primary_intent="query",
        items=(MessageItem(type="query", text="Какие правила?"),),
    )
    classifier = StubClassifier(
        configured_results={
            ("Какие правила?", "open"): intake,
        }
    )

    result = classifier.classify("Какие правила?", "open")

    assert result is intake


def test_dev_classifier_task_command() -> None:
    classifier = DevCommandClassifier()

    result = classifier.classify("/task Проверить код", "open")

    assert result.primary_intent == "task"
    assert result.items == (MessageItem(type="task", text="Проверить код"),)


def test_dev_classifier_rule_command() -> None:
    classifier = DevCommandClassifier()

    result = classifier.classify("/rule Показывай понимание", "open")

    assert result.primary_intent == "rule_update"
    assert result.items == (
        MessageItem(
            type="rule_candidate",
            text="Показывай понимание",
            scope="all_tasks",
            key="show_understanding_before_execution",
        ),
    )


def test_dev_classifier_future_rule_command() -> None:
    classifier = DevCommandClassifier()

    result = classifier.classify("/future-rule Не сохраняй это как активное", "open")

    assert result.primary_intent == "rule_update"
    assert result.items == (
        MessageItem(
            type="rule_candidate",
            text="Не сохраняй это как активное",
            scope="all_tasks",
            key=None,
        ),
    )


def test_dev_classifier_query_command() -> None:
    classifier = DevCommandClassifier()

    result = classifier.classify("/query", "open")

    assert result.primary_intent == "query"
    assert result.items == (MessageItem(type="query", text="program_current"),)


def test_dev_classifier_ambiguous_command() -> None:
    classifier = DevCommandClassifier()

    result = classifier.classify("/ambiguous Сделай как надо", "open")

    assert result.primary_intent == "chat"
    assert result.items == (MessageItem(type="ambiguous_request", text="Сделай как надо"),)


def test_dev_classifier_plain_text_is_chat() -> None:
    classifier = DevCommandClassifier()

    result = classifier.classify("Привет, как дела?", "open")

    assert result.primary_intent == "chat"
    assert result.items == ()


def test_no_production_keyword_semantic_router() -> None:
    assert "LLMClassifier" not in globals()
    assert "KeywordClassifier" not in globals()
