"""Contract: pure validation helpers for MVP item semantics and review flags."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace

from jeeves_dap.domain.agent_program import KNOWN_RULE_KEYS
from jeeves_dap.domain.models import IntakeResult, MessageItem, ReviewFlags


@dataclass(frozen=True, slots=True)
class ItemValidationResult:
    """Contract: validation result that returns a normalized item plus machine-readable status."""

    is_valid: bool
    normalized_item: MessageItem
    reason: str | None = None
    needs_clarification: bool = False


def derive_rule_application_mode(key: str | None) -> str:
    """Contract: map a rule key to the only MVP application modes."""

    if key in KNOWN_RULE_KEYS:
        return "enforced_by_rule_engine"
    return "future_rule"


def validate_item(item: MessageItem) -> ItemValidationResult:
    """Contract: validate one item and normalize unsupported rules to future_rule."""

    if item.type in {"task", "rule_candidate", "correction", "feedback"} and not item.text.strip():
        return ItemValidationResult(
            is_valid=False,
            normalized_item=item,
            reason="empty_text",
        )

    if item.type == "rule_candidate":
        if not item.scope:
            return ItemValidationResult(
                is_valid=False,
                normalized_item=item,
                reason="missing_scope",
            )

        return ItemValidationResult(
            is_valid=True,
            normalized_item=replace(
                item,
                application_mode=derive_rule_application_mode(item.key),
            ),
        )

    if item.type == "ambiguous_request":
        return ItemValidationResult(
            is_valid=True,
            normalized_item=item,
            reason="ambiguous_request",
            needs_clarification=True,
        )

    return ItemValidationResult(
        is_valid=True,
        normalized_item=item,
    )


def compute_understanding_sufficiency(intake: IntakeResult) -> bool:
    """Contract: compute mandatory-field sufficiency from primary intent and normalized items."""

    validations = [validate_item(item) for item in intake.items]

    def has_valid_item(item_type: str) -> bool:
        return any(
            validation.is_valid and validation.normalized_item.type == item_type
            for validation in validations
        )

    has_ambiguous_request = any(validation.needs_clarification for validation in validations)

    if intake.primary_intent == "task":
        return has_valid_item("task")
    if intake.primary_intent == "rule_update":
        return has_valid_item("rule_candidate")
    if intake.primary_intent == "correction":
        return has_valid_item("correction")
    if intake.primary_intent == "feedback":
        return has_valid_item("feedback")
    if intake.primary_intent in {"query", "cancel"}:
        return True
    if intake.primary_intent == "chat":
        return not has_ambiguous_request
    return False


def derive_review_flags(intake: IntakeResult) -> ReviewFlags:
    """Contract: derive mutually exclusive review flags for MVP orchestration."""

    validations = [validate_item(item) for item in intake.items]
    is_sufficient = compute_understanding_sufficiency(intake)

    needs_clarification = (
        any(validation.needs_clarification for validation in validations) or not is_sufficient
    )
    requires_user_review = False

    if not needs_clarification:
        requires_user_review = any(
            validation.is_valid and validation.normalized_item.type == "rule_candidate"
            for validation in validations
        )

    return ReviewFlags(
        requires_user_review=requires_user_review,
        needs_clarification=needs_clarification,
    )
