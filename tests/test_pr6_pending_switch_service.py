"""Contract: PR-6 regression tests for pending switch confirmation and deferred message flow."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from jeeves_dap.domain.models import Episode, IntakeResult, MessageItem, UserMessage
from jeeves_dap.repositories.agent_program_repository import InMemoryAgentProgramVersionRepository
from jeeves_dap.repositories.deferred_message_repository import InMemoryDeferredMessageRepository
from jeeves_dap.services.agent_program_service import AgentProgramService
from jeeves_dap.services.pending_switch_service import PendingSwitchService


def build_episode(state: str) -> Episode:
    return Episode(
        id="e1",
        user_id="u1",
        state=state,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def build_message(message_id: str, text: str) -> UserMessage:
    return UserMessage(
        id=message_id,
        episode_id="e1",
        text=text,
        created_at=datetime.now(UTC),
    )


def test_should_request_switch_from_pending_understanding_for_new_task() -> None:
    service = PendingSwitchService(InMemoryDeferredMessageRepository())
    episode = build_episode("pending_understanding_review")
    intake = IntakeResult(
        message_id="m1",
        primary_intent="task",
        items=(MessageItem(type="task", text="Проверить код"),),
    )

    assert service.should_request_switch(episode, intake) is True


def test_should_request_switch_from_pending_rule_for_new_query() -> None:
    service = PendingSwitchService(InMemoryDeferredMessageRepository())
    episode = build_episode("pending_rule_review")
    intake = IntakeResult(message_id="m1", primary_intent="query", items=())

    assert service.should_request_switch(episode, intake) is True


def test_should_not_request_switch_from_open_state() -> None:
    service = PendingSwitchService(InMemoryDeferredMessageRepository())
    episode = build_episode("open")
    intake = IntakeResult(message_id="m1", primary_intent="task", items=())

    assert service.should_request_switch(episode, intake) is False


def test_should_not_request_switch_for_correction() -> None:
    service = PendingSwitchService(InMemoryDeferredMessageRepository())
    episode = build_episode("pending_understanding_review")
    intake = IntakeResult(
        message_id="m1",
        primary_intent="correction",
        items=(MessageItem(type="correction", text="Не это имел в виду"),),
    )

    assert service.should_request_switch(episode, intake) is False


def test_should_not_request_switch_for_feedback() -> None:
    service = PendingSwitchService(InMemoryDeferredMessageRepository())
    episode = build_episode("pending_rule_review")
    intake = IntakeResult(
        message_id="m1",
        primary_intent="feedback",
        items=(MessageItem(type="feedback", text="Хорошо"),),
    )

    assert service.should_request_switch(episode, intake) is False


def test_should_not_request_switch_for_cancel() -> None:
    service = PendingSwitchService(InMemoryDeferredMessageRepository())
    episode = build_episode("pending_rule_review")
    intake = IntakeResult(message_id="m1", primary_intent="cancel", items=())

    assert service.should_request_switch(episode, intake) is False


def test_should_not_request_switch_when_related_to_pending() -> None:
    service = PendingSwitchService(InMemoryDeferredMessageRepository())
    episode = build_episode("pending_understanding_review")
    intake = IntakeResult(message_id="m1", primary_intent="task", items=())

    assert service.should_request_switch(episode, intake, is_related_to_pending=True) is False


def test_request_switch_saves_deferred_message() -> None:
    repository = InMemoryDeferredMessageRepository()
    service = PendingSwitchService(repository)
    episode = build_episode("pending_rule_review")
    message = build_message("m2", "А какая сейчас погода?")
    intake = IntakeResult(message_id="m2", primary_intent="query", items=())

    decision = service.request_switch(
        episode,
        message,
        intake,
        deferred_id="d1",
        created_at=datetime.now(UTC),
    )

    assert repository.get_by_episode_id("e1") == decision.deferred_message


def test_request_switch_sets_episode_pending_switch_confirmation() -> None:
    service = PendingSwitchService(InMemoryDeferredMessageRepository())
    episode = build_episode("pending_understanding_review")
    message = build_message("m2", "А какая сейчас погода?")
    intake = IntakeResult(message_id="m2", primary_intent="query", items=())

    decision = service.request_switch(
        episode,
        message,
        intake,
        deferred_id="d1",
        created_at=datetime.now(UTC),
    )

    assert decision.episode.state == "pending_switch_confirmation"


def test_request_switch_response_mentions_new_message_not_new_task() -> None:
    service = PendingSwitchService(InMemoryDeferredMessageRepository())
    episode = build_episode("pending_rule_review")
    message = build_message("m2", "А какая сейчас погода?")
    intake = IntakeResult(message_id="m2", primary_intent="query", items=())

    decision = service.request_switch(
        episode,
        message,
        intake,
        deferred_id="d1",
        created_at=datetime.now(UTC),
    )

    assert "новому сообщению" in decision.assistant_response or "новой теме" in decision.assistant_response
    assert "новой задаче" not in decision.assistant_response


def test_pending_switch_confirm_process_deferred_false_for_mvp() -> None:
    repository = InMemoryDeferredMessageRepository()
    service = PendingSwitchService(repository)
    episode = build_episode("pending_switch_confirmation")
    repository.save(
        replace(
            service.request_switch(
                build_episode("pending_rule_review"),
                build_message("m2", "А какая сейчас погода?"),
                IntakeResult(message_id="m2", primary_intent="query", items=()),
                deferred_id="d1",
                created_at=datetime.now(UTC),
            ).deferred_message
        )
    )

    decision = service.confirm_switch(episode)

    assert decision.process_deferred is False


def test_confirm_switch_cancels_pending_episode() -> None:
    repository = InMemoryDeferredMessageRepository()
    service = PendingSwitchService(repository)
    repository.save(
        service.request_switch(
            build_episode("pending_understanding_review"),
            build_message("m2", "Новая тема"),
            IntakeResult(message_id="m2", primary_intent="chat", items=()),
            deferred_id="d1",
            created_at=datetime.now(UTC),
        ).deferred_message
    )

    decision = service.confirm_switch(build_episode("pending_switch_confirmation"))

    assert decision.action == "pending_cancelled_by_user_switch"
    assert decision.episode.state == "cancelled"


def test_pending_switch_confirm_does_not_claim_deferred_was_processed() -> None:
    repository = InMemoryDeferredMessageRepository()
    service = PendingSwitchService(repository)
    repository.save(
        service.request_switch(
            build_episode("pending_rule_review"),
            build_message("m2", "Новая тема"),
            IntakeResult(message_id="m2", primary_intent="chat", items=()),
            deferred_id="d1",
            created_at=datetime.now(UTC),
        ).deferred_message
    )

    decision = service.confirm_switch(build_episode("pending_switch_confirmation"))

    assert "отправьте новое сообщение ещё раз" in decision.assistant_response.lower()
    assert "продолжаю с новым сообщением" not in decision.assistant_response.lower()


def test_reject_switch_restores_pending_understanding_review() -> None:
    repository = InMemoryDeferredMessageRepository()
    service = PendingSwitchService(repository)
    repository.save(
        service.request_switch(
            build_episode("pending_understanding_review"),
            build_message("m2", "Новая тема"),
            IntakeResult(message_id="m2", primary_intent="chat", items=()),
            deferred_id="d1",
            created_at=datetime.now(UTC),
        ).deferred_message
    )

    decision = service.reject_switch(build_episode("pending_switch_confirmation"))

    assert decision.episode.state == "pending_understanding_review"
    assert repository.get_by_episode_id("e1") is None


def test_reject_switch_restores_pending_rule_review() -> None:
    repository = InMemoryDeferredMessageRepository()
    service = PendingSwitchService(repository)
    repository.save(
        service.request_switch(
            build_episode("pending_rule_review"),
            build_message("m2", "Новая тема"),
            IntakeResult(message_id="m2", primary_intent="chat", items=()),
            deferred_id="d1",
            created_at=datetime.now(UTC),
        ).deferred_message
    )

    decision = service.reject_switch(build_episode("pending_switch_confirmation"))

    assert decision.episode.state == "pending_rule_review"
    assert repository.get_by_episode_id("e1") is None


def test_cancel_episode_cancels_and_deletes_deferred() -> None:
    repository = InMemoryDeferredMessageRepository()
    service = PendingSwitchService(repository)
    repository.save(
        service.request_switch(
            build_episode("pending_understanding_review"),
            build_message("m2", "Новая тема"),
            IntakeResult(message_id="m2", primary_intent="chat", items=()),
            deferred_id="d1",
            created_at=datetime.now(UTC),
        ).deferred_message
    )

    decision = service.cancel_episode(build_episode("pending_switch_confirmation"))

    assert decision.episode.state == "cancelled"
    assert repository.get_by_episode_id("e1") is None


def test_pending_switch_does_not_mutate_agent_program() -> None:
    repository = InMemoryAgentProgramVersionRepository()
    program_service = AgentProgramService(repository)
    active_version = program_service.create_initial_version("v1", datetime.now(UTC))
    deferred_repository = InMemoryDeferredMessageRepository()
    service = PendingSwitchService(deferred_repository)
    episode = build_episode("pending_rule_review")
    message = build_message("m2", "Новая тема")
    intake = IntakeResult(message_id="m2", primary_intent="chat", items=())

    service.request_switch(
        episode,
        message,
        intake,
        deferred_id="d1",
        created_at=datetime.now(UTC),
    )

    assert active_version.version_number == 1
    assert active_version.program.rules == ()


def test_domain_layer_does_not_import_services_or_repositories() -> None:
    for path in (
        "src/jeeves_dap/domain/agent_program.py",
        "src/jeeves_dap/domain/models.py",
        "src/jeeves_dap/domain/validation.py",
    ):
        with open(path, encoding="utf-8") as file:
            source = file.read()

        assert "jeeves_dap.services" not in source
        assert "jeeves_dap.repositories" not in source
