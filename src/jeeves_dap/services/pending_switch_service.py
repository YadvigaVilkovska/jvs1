"""Contract: service-level pending switch confirmation flow without orchestration or side effects."""

from __future__ import annotations

from dataclasses import replace

from jeeves_dap.domain.models import DeferredMessage, Episode, IntakeResult, PendingSwitchDecision, UserMessage
from jeeves_dap.repositories.deferred_message_repository import DeferredMessageRepository

SWITCH_RESPONSE_TEXT = (
    "У нас осталось неподтверждённое правило/понимание. "
    "Если перейти к новому сообщению или новой теме, оно будет отменено. "
    "Отменить его и продолжить с новым сообщением?"
)


class PendingSwitchService:
    """Contract: decide, persist, and resolve pending switch confirmation flow."""

    def __init__(self, deferred_repository: DeferredMessageRepository) -> None:
        self._deferred_repository = deferred_repository

    def should_request_switch(
        self,
        episode: Episode,
        intake: IntakeResult,
        is_related_to_pending: bool = False,
    ) -> bool:
        """Return true only for unrelated semantic messages arriving during pending review states."""

        if episode.state not in {"pending_understanding_review", "pending_rule_review"}:
            return False
        if intake.primary_intent in {"correction", "feedback", "cancel"}:
            return False
        if is_related_to_pending:
            return False
        return intake.primary_intent in {"task", "query", "rule_update", "chat"}

    def request_switch(
        self,
        episode: Episode,
        incoming_message: UserMessage,
        intake: IntakeResult,
        deferred_id: str,
        created_at,
    ) -> PendingSwitchDecision:
        """Persist a deferred message and move the episode into switch confirmation state."""

        deferred_message = DeferredMessage(
            id=deferred_id,
            episode_id=episode.id,
            message_id=incoming_message.id,
            intake_result=intake,
            created_at=created_at,
            previous_episode_state=episode.state,
        )
        self._deferred_repository.save(deferred_message)

        updated_episode = replace(episode, state="pending_switch_confirmation", updated_at=created_at)
        return PendingSwitchDecision(
            action="pending_switch_requested",
            episode=updated_episode,
            assistant_response=SWITCH_RESPONSE_TEXT,
            deferred_message=deferred_message,
            process_deferred=False,
        )

    def confirm_switch(self, episode: Episode) -> PendingSwitchDecision:
        """Cancel the pending object and ask the user to resend the deferred message explicitly."""

        deferred_message = self._deferred_repository.get_by_episode_id(episode.id)
        self._deferred_repository.delete_by_episode_id(episode.id)
        updated_episode = replace(episode, state="cancelled")
        return PendingSwitchDecision(
            action="pending_cancelled_by_user_switch",
            episode=updated_episode,
            assistant_response="Неподтверждённое правило/понимание отменено. Отправьте новое сообщение ещё раз.",
            deferred_message=deferred_message,
            process_deferred=False,
        )

    def reject_switch(self, episode: Episode) -> PendingSwitchDecision:
        """Return to the stored pending state and clear the rejected deferred switch request."""

        deferred_message = self._deferred_repository.get_by_episode_id(episode.id)
        previous_state = (
            deferred_message.previous_episode_state
            if deferred_message is not None and deferred_message.previous_episode_state is not None
            else "pending_rule_review"
        )
        self._deferred_repository.delete_by_episode_id(episode.id)
        updated_episode = replace(episode, state=previous_state)
        return PendingSwitchDecision(
            action="pending_switch_rejected",
            episode=updated_episode,
            assistant_response="Хорошо, остаёмся на текущем неподтверждённом правиле/понимании.",
            deferred_message=None,
            process_deferred=False,
        )

    def cancel_episode(self, episode: Episode) -> PendingSwitchDecision:
        """Cancel the episode and clear any deferred message."""

        self._deferred_repository.delete_by_episode_id(episode.id)
        updated_episode = replace(episode, state="cancelled")
        return PendingSwitchDecision(
            action="episode_cancelled_by_user",
            episode=updated_episode,
            assistant_response="Эпизод отменён.",
            deferred_message=None,
            process_deferred=False,
        )
