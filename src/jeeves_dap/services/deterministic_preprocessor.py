"""Contract: exact short command pre-processing without any semantic keyword routing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from jeeves_dap.domain.models import EpisodeState

CONFIRM_COMMANDS: frozenset[str] = frozenset(
    {
        "да",
        "верно",
        "подтверждаю",
        "так",
        "сохрани",
        "конечно",
    }
)

REJECT_COMMANDS: frozenset[str] = frozenset(
    {
        "нет",
        "не так",
        "не подтверждаю",
        "не сохраняй",
        "не нужно",
    }
)

CANCEL_COMMANDS: frozenset[str] = frozenset(
    {
        "отмена",
        "забудь",
        "начнём заново",
        "начать заново",
        "отменить",
    }
)

BOUNDARY_PUNCTUATION_PATTERN = re.compile(r"^[\s.,!?;:'\"(){}\[\]<>«»“”‘’`~\-]+|[\s.,!?;:'\"(){}\[\]<>«»“”‘’`~\-]+$")
REPEATED_WHITESPACE_PATTERN = re.compile(r"\s+")
PENDING_CONFIRMATION_STATES: frozenset[EpisodeState] = frozenset(
    {
        "pending_understanding_review",
        "pending_rule_review",
        "pending_switch_confirmation",
    }
)


@dataclass(frozen=True, slots=True)
class PreprocessResult:
    """Contract: deterministic control action extracted before semantic classification."""

    action: str
    normalized_text: str


class DeterministicPreProcessor:
    """Contract: recognize only exact short control commands after deterministic normalization."""

    def normalize_command(self, text: str) -> str:
        """Normalize casing, spaces, and boundary punctuation without substring matching."""

        lowered = text.lower().strip()
        collapsed = REPEATED_WHITESPACE_PATTERN.sub(" ", lowered)
        stripped = BOUNDARY_PUNCTUATION_PATTERN.sub("", collapsed)
        return REPEATED_WHITESPACE_PATTERN.sub(" ", stripped).strip()

    def preprocess(self, text: str, episode_state: EpisodeState) -> PreprocessResult | None:
        """Return a deterministic control action only for exact full-string command matches."""

        normalized_text = self.normalize_command(text)

        if normalized_text in CANCEL_COMMANDS:
            return PreprocessResult(action="cancel", normalized_text=normalized_text)

        if episode_state in PENDING_CONFIRMATION_STATES:
            if normalized_text in CONFIRM_COMMANDS:
                return PreprocessResult(action="confirm", normalized_text=normalized_text)
            if normalized_text in REJECT_COMMANDS:
                return PreprocessResult(action="reject", normalized_text=normalized_text)

        return None
