"""Contract: classifier abstractions for semantic parsing without production routing logic."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Any, get_args

from jeeves_dap.domain.models import (
    EpisodeState,
    IntakeResult,
    MessageItem,
    MessageItemType,
    ModelRoutePair,
    PrimaryIntent,
)
from jeeves_dap.services.model_routing import ModelRouter

DEV_PLACEHOLDER_MESSAGE_ID = "dev-command"
LLM_INTAKE_MESSAGE_ID = "llm-intake"
LLM_INTAKE_ERROR_MESSAGE_ID = "llm-intake-error"
TASK_COMMAND_PREFIX = "/task "
RULE_COMMAND_PREFIX = "/rule "
FUTURE_RULE_COMMAND_PREFIX = "/future-rule "
QUERY_COMMAND = "/query"
AMBIGUOUS_COMMAND_PREFIX = "/ambiguous "
SUPPORTED_PRIMARY_INTENTS = frozenset(get_args(PrimaryIntent))
SUPPORTED_MESSAGE_ITEM_TYPES = frozenset(get_args(MessageItemType))


class IntentClassifier(ABC):
    """Contract: semantic classifier interface implemented by test stubs or future LLM adapters."""

    @abstractmethod
    def classify(self, text: str, episode_state: EpisodeState) -> IntakeResult:
        """Return a structured intake result for one message."""


class LLMIntakeClient(ABC):
    """Contract: injected intake client seam that returns structured parsing output only."""

    @abstractmethod
    def classify_text(
        self,
        text: str,
        route: ModelRoutePair,
        message_id: str,
    ) -> IntakeResult | dict[str, Any]:
        """Return one intake result payload for current text and intake route."""


class StubLLMIntakeClient(LLMIntakeClient):
    """Contract: test intake client that records calls and returns configured structured output."""

    def __init__(
        self,
        *,
        result: IntakeResult | dict[str, Any] | None = None,
        exception: Exception | None = None,
    ) -> None:
        self._result = result
        self._exception = exception
        self.calls = 0
        self.received_text: str | None = None
        self.received_route: ModelRoutePair | None = None
        self.received_message_id: str | None = None

    def classify_text(
        self,
        text: str,
        route: ModelRoutePair,
        message_id: str,
    ) -> IntakeResult | dict[str, Any]:
        self.calls += 1
        self.received_text = text
        self.received_route = route
        self.received_message_id = message_id
        if self._exception is not None:
            raise self._exception
        if self._result is None:
            raise ValueError("StubLLMIntakeClient requires result or exception")
        return self._result


class StubClassifier(IntentClassifier):
    """Contract: test double that returns preconfigured intake results without semantic routing."""

    def __init__(
        self,
        configured_results: dict[tuple[str, EpisodeState], IntakeResult] | None = None,
        default_result: IntakeResult | None = None,
    ) -> None:
        self._configured_results = configured_results or {}
        self._default_result = default_result

    def classify(self, text: str, episode_state: EpisodeState) -> IntakeResult:
        key = (text, episode_state)
        if key in self._configured_results:
            return self._configured_results[key]
        if self._default_result is not None:
            return self._default_result
        raise KeyError(f"No configured IntakeResult for text={text!r}, episode_state={episode_state!r}")


class LLMIntakeClassifier(IntentClassifier):
    """Contract: intake-only classifier that routes current text through an injected model/client seam."""

    def __init__(self, model_router: ModelRouter, client: LLMIntakeClient) -> None:
        self._model_router = model_router
        self._client = client

    def classify(self, text: str, episode_state: EpisodeState) -> IntakeResult:
        del episode_state
        try:
            route = self._model_router.get_route("intake")
            raw_result = self._client.classify_text(text, route, LLM_INTAKE_MESSAGE_ID)
            parsed = self._parse_result(raw_result)
            return replace(parsed, message_id=LLM_INTAKE_MESSAGE_ID)
        except Exception:
            return IntakeResult(
                message_id=LLM_INTAKE_ERROR_MESSAGE_ID,
                primary_intent="chat",
                items=(MessageItem(type="ambiguous_request", text=text),),
            )

    @staticmethod
    def _parse_result(raw_result: IntakeResult | dict[str, Any]) -> IntakeResult:
        """Contract: parse one client payload into IntakeResult or fail closed."""

        if isinstance(raw_result, IntakeResult):
            _validate_primary_intent(raw_result.primary_intent)
            for item in raw_result.items:
                _validate_message_item_type(item.type)
            return raw_result
        if not isinstance(raw_result, dict):
            raise ValueError("LLM intake output must be IntakeResult or dict")

        raw_primary_intent = raw_result["primary_intent"]
        _validate_primary_intent(raw_primary_intent)

        raw_items = raw_result["items"]
        if not isinstance(raw_items, list):
            raise ValueError("LLM intake items must be list")

        items = tuple(
            MessageItem(
                type=_parse_message_item_type(item["type"]),
                text=item["text"],
                scope=item.get("scope"),
                key=item.get("key"),
                application_mode=item.get("application_mode"),
                confidence=item.get("confidence"),
            )
            for item in raw_items
        )
        return IntakeResult(
            message_id=str(raw_result.get("message_id", LLM_INTAKE_MESSAGE_ID)),
            primary_intent=raw_primary_intent,
            items=items,
        )


class DevCommandClassifier(IntentClassifier):
    """Contract: dev-only explicit slash-command protocol for local manual testing."""

    def classify(self, text: str, episode_state: EpisodeState) -> IntakeResult:
        normalized_text = text.strip()

        if normalized_text.startswith(TASK_COMMAND_PREFIX):
            task_text = normalized_text[len(TASK_COMMAND_PREFIX) :].strip()
            return IntakeResult(
                message_id=DEV_PLACEHOLDER_MESSAGE_ID,
                primary_intent="task",
                items=(MessageItem(type="task", text=task_text),),
            )

        if normalized_text.startswith(RULE_COMMAND_PREFIX):
            rule_text = normalized_text[len(RULE_COMMAND_PREFIX) :].strip()
            return IntakeResult(
                message_id=DEV_PLACEHOLDER_MESSAGE_ID,
                primary_intent="rule_update",
                items=(
                    MessageItem(
                        type="rule_candidate",
                        text=rule_text,
                        scope="all_tasks",
                        key="show_understanding_before_execution",
                    ),
                ),
            )

        if normalized_text.startswith(FUTURE_RULE_COMMAND_PREFIX):
            rule_text = normalized_text[len(FUTURE_RULE_COMMAND_PREFIX) :].strip()
            return IntakeResult(
                message_id=DEV_PLACEHOLDER_MESSAGE_ID,
                primary_intent="rule_update",
                items=(
                    MessageItem(
                        type="rule_candidate",
                        text=rule_text,
                        scope="all_tasks",
                        key=None,
                    ),
                ),
            )

        if normalized_text == QUERY_COMMAND:
            return IntakeResult(
                message_id=DEV_PLACEHOLDER_MESSAGE_ID,
                primary_intent="query",
                items=(MessageItem(type="query", text="program_current"),),
            )

        if normalized_text.startswith(AMBIGUOUS_COMMAND_PREFIX):
            ambiguous_text = normalized_text[len(AMBIGUOUS_COMMAND_PREFIX) :].strip()
            return IntakeResult(
                message_id=DEV_PLACEHOLDER_MESSAGE_ID,
                primary_intent="chat",
                items=(MessageItem(type="ambiguous_request", text=ambiguous_text),),
            )

        return IntakeResult(
            message_id=DEV_PLACEHOLDER_MESSAGE_ID,
            primary_intent="chat",
            items=(),
        )


def _validate_primary_intent(primary_intent: str) -> None:
    """Contract: reject unsupported or explicitly banned primary intent values."""

    if primary_intent == "mixed" or primary_intent not in SUPPORTED_PRIMARY_INTENTS:
        raise ValueError(f"Unsupported primary_intent: {primary_intent}")


def _validate_message_item_type(item_type: str) -> None:
    """Contract: reject unsupported semantic item types before domain object creation."""

    if item_type not in SUPPORTED_MESSAGE_ITEM_TYPES:
        raise ValueError(f"Unsupported item type: {item_type}")


def _parse_message_item_type(item_type: str) -> str:
    """Contract: validate and return one supported message item type."""

    _validate_message_item_type(item_type)
    return item_type
