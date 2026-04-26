"""Contract: PR-2 regression tests for deterministic command handling and classifier seams."""

from __future__ import annotations

from abc import ABC
from pathlib import Path
from typing import get_type_hints
import inspect

from jeeves_dap.domain.models import IntakeResult, MessageItem
from jeeves_dap.services.classification import DevCommandClassifier, IntentClassifier, StubClassifier
from jeeves_dap.services.deterministic_preprocessor import (
    CANCEL_COMMANDS,
    CONFIRM_COMMANDS,
    REJECT_COMMANDS,
    DeterministicPreProcessor,
)
from jeeves_dap.services.model_routing import (
    ModelRouter,
    build_default_model_routing_config,
    build_model_routing_config_from_env,
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


def test_default_intake_primary_is_openai_gpt_4o_mini() -> None:
    config = build_default_model_routing_config()

    assert config.intake.primary.provider == "openai"
    assert config.intake.primary.model == "gpt-4o-mini"


def test_default_intake_fallback_is_deepseek_chat() -> None:
    config = build_default_model_routing_config()

    assert config.intake.fallback.provider == "deepseek"
    assert config.intake.fallback.model == "deepseek-chat"


def test_default_work_primary_is_deepseek_reasoner() -> None:
    config = build_default_model_routing_config()

    assert config.work.primary.provider == "deepseek"
    assert config.work.primary.model == "deepseek-reasoner"


def test_default_work_fallback_is_openai_gpt_5_5() -> None:
    config = build_default_model_routing_config()

    assert config.work.fallback.provider == "openai"
    assert config.work.fallback.model == "gpt-5.5"


def test_model_router_returns_primary_and_fallback_for_intake() -> None:
    router = ModelRouter(build_default_model_routing_config())

    route = router.get_route("intake")

    assert route.primary.provider == "openai"
    assert route.primary.model == "gpt-4o-mini"
    assert route.fallback.provider == "deepseek"
    assert route.fallback.model == "deepseek-chat"


def test_model_router_returns_primary_and_fallback_for_work() -> None:
    router = ModelRouter(build_default_model_routing_config())

    route = router.get_route("work")

    assert route.primary.provider == "deepseek"
    assert route.primary.model == "deepseek-reasoner"
    assert route.fallback.provider == "openai"
    assert route.fallback.model == "gpt-5.5"


def test_environment_overrides_intake_route() -> None:
    config = build_model_routing_config_from_env(
        {
            "INTAKE_PRIMARY_PROVIDER": "deepseek",
            "INTAKE_PRIMARY_MODEL": "deepseek-chat",
            "INTAKE_FALLBACK_PROVIDER": "openai",
            "INTAKE_FALLBACK_MODEL": "gpt-5.5",
        }
    )

    assert config.intake.primary.provider == "deepseek"
    assert config.intake.primary.model == "deepseek-chat"
    assert config.intake.fallback.provider == "openai"
    assert config.intake.fallback.model == "gpt-5.5"


def test_environment_overrides_work_route() -> None:
    config = build_model_routing_config_from_env(
        {
            "WORK_PRIMARY_PROVIDER": "openai",
            "WORK_PRIMARY_MODEL": "gpt-4o-mini",
            "WORK_FALLBACK_PROVIDER": "deepseek",
            "WORK_FALLBACK_MODEL": "deepseek-chat",
        }
    )

    assert config.work.primary.provider == "openai"
    assert config.work.primary.model == "gpt-4o-mini"
    assert config.work.fallback.provider == "deepseek"
    assert config.work.fallback.model == "deepseek-chat"


def test_router_rejects_unknown_role_or_invalid_provider_if_applicable() -> None:
    router = ModelRouter(build_default_model_routing_config())

    try:
        router.get_route("unknown")
    except ValueError as error:
        assert "Unknown model role" in str(error)
    else:
        raise AssertionError("Expected ValueError for unknown role")

    try:
        build_model_routing_config_from_env({"INTAKE_PRIMARY_PROVIDER": "invalid"})
    except ValueError as error:
        assert "Unsupported provider" in str(error)
    else:
        raise AssertionError("Expected ValueError for invalid provider")


def test_no_real_llm_api_calls_are_made() -> None:
    source = Path("src/jeeves_dap/services/model_routing.py").read_text(encoding="utf-8")

    assert "requests" not in source
    assert "httpx" not in source
    assert "OpenAI" not in source
    assert "AsyncOpenAI" not in source
    assert "DeepSeek" not in source


def test_existing_dev_command_classifier_still_works() -> None:
    classifier = DevCommandClassifier()

    result = classifier.classify("/task Проверить код", "open")

    assert result.primary_intent == "task"
    assert result.items == (MessageItem(type="task", text="Проверить код"),)
