"""Contract: classifier abstractions for semantic parsing without production routing logic."""

from __future__ import annotations

from abc import ABC, abstractmethod

from jeeves_dap.domain.models import EpisodeState, IntakeResult, MessageItem

DEV_PLACEHOLDER_MESSAGE_ID = "dev-command"
TASK_COMMAND_PREFIX = "/task "
RULE_COMMAND_PREFIX = "/rule "
FUTURE_RULE_COMMAND_PREFIX = "/future-rule "
QUERY_COMMAND = "/query"
AMBIGUOUS_COMMAND_PREFIX = "/ambiguous "


class IntentClassifier(ABC):
    """Contract: semantic classifier interface implemented by test stubs or future LLM adapters."""

    @abstractmethod
    def classify(self, text: str, episode_state: EpisodeState) -> IntakeResult:
        """Return a structured intake result for one message."""


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
