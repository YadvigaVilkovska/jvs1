"""Contract: PR-7 regression tests for the service-level orchestrator vertical slice."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import inspect
from pathlib import Path

from jeeves_dap.domain.models import (
    Episode,
    IntakeResult,
    MessageItem,
    PendingUnderstanding,
    RuntimeTask,
    UserMessage,
)
from jeeves_dap.repositories.agent_program_repository import InMemoryAgentProgramVersionRepository
from jeeves_dap.repositories.deferred_message_repository import InMemoryDeferredMessageRepository
from jeeves_dap.repositories.pending_understanding_repository import InMemoryPendingUnderstandingRepository
from jeeves_dap.repositories.rule_candidate_repository import InMemoryRuleCandidateRepository
from jeeves_dap.repositories.unknown_utterance_repository import InMemoryUnknownUtteranceRepository
from jeeves_dap.services.agent_program_service import AgentProgramService
from jeeves_dap.services.classification import IntentClassifier, StubClassifier
from jeeves_dap.services.deterministic_preprocessor import DeterministicPreProcessor
from jeeves_dap.services.orchestrator import Orchestrator
from jeeves_dap.services.pending_switch_service import PendingSwitchService
from jeeves_dap.services.rule_engine import RuleEngine
from jeeves_dap.services.task_runtime_stub import TaskRuntimeStub
from jeeves_dap.services.verifier_stub import VerifierStub


class TrackingClassifier(IntentClassifier):
    """Contract: test classifier that counts classify calls without any semantic routing."""

    def __init__(self, result: IntakeResult) -> None:
        self.result = result
        self.calls = 0

    def classify(self, text: str, episode_state: str) -> IntakeResult:
        self.calls += 1
        return self.result


def build_orchestrator(
    classifier: IntentClassifier,
) -> tuple[
    Orchestrator,
    AgentProgramService,
    InMemoryUnknownUtteranceRepository,
    InMemoryDeferredMessageRepository,
    InMemoryRuleCandidateRepository,
    InMemoryPendingUnderstandingRepository,
]:
    program_repository = InMemoryAgentProgramVersionRepository()
    program_service = AgentProgramService(program_repository)
    unknown_repository = InMemoryUnknownUtteranceRepository()
    deferred_repository = InMemoryDeferredMessageRepository()
    rule_candidate_repository = InMemoryRuleCandidateRepository()
    pending_understanding_repository = InMemoryPendingUnderstandingRepository()
    orchestrator = Orchestrator(
        classifier=classifier,
        preprocessor=DeterministicPreProcessor(),
        program_service=program_service,
        rule_candidate_repository=rule_candidate_repository,
        pending_understanding_repository=pending_understanding_repository,
        unknown_utterance_repository=unknown_repository,
        pending_switch_service=PendingSwitchService(deferred_repository),
        task_runtime=TaskRuntimeStub(RuleEngine(), VerifierStub()),
    )
    return (
        orchestrator,
        program_service,
        unknown_repository,
        deferred_repository,
        rule_candidate_repository,
        pending_understanding_repository,
    )


def build_episode(state: str = "open") -> Episode:
    return Episode(
        id="e1",
        user_id="u1",
        state=state,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def build_message(text: str, message_id: str = "m1") -> UserMessage:
    return UserMessage(
        id=message_id,
        episode_id="e1",
        text=text,
        created_at=datetime.now(UTC),
    )


def build_active_program_version(program_service: AgentProgramService):
    return program_service.create_initial_version("v1", datetime.now(UTC))


def test_orchestrator_runs_preprocessor_before_classifier() -> None:
    classifier = TrackingClassifier(
        IntakeResult(message_id="m1", primary_intent="query", items=())
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)

    result = orchestrator.handle_message(
        build_episode("pending_rule_review"),
        build_message("отмена"),
        build_active_program_version(program_service),
    )

    assert classifier.calls == 0
    assert result.episode.state == "cancelled"


def test_orchestrator_confirmation_flow_not_bypassed() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
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
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)

    result = orchestrator.handle_message(
        build_episode(),
        build_message("/rule Показывай понимание"),
        active_version,
    )

    assert result.program_version == active_version
    assert result.episode.state == "pending_rule_review"


def test_orchestrator_cancel_message_cancels_episode() -> None:
    classifier = StubClassifier(default_result=IntakeResult(message_id="m1", primary_intent="chat", items=()))
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)

    result = orchestrator.handle_message(
        build_episode("pending_switch_confirmation"),
        build_message("отмена"),
        build_active_program_version(program_service),
    )

    assert result.episode.state == "cancelled"
    assert result.pending_switch_decision is not None


def test_orchestrator_missing_task_fields_records_unknown_and_does_not_execute() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="query", text="Что сейчас активно?"),),
        )
    )
    orchestrator, program_service, unknown_repository, _, _, _ = build_orchestrator(classifier)

    result = orchestrator.handle_message(
        build_episode(),
        build_message("Сделай"),
        build_active_program_version(program_service),
    )

    assert result.runtime_result is None
    assert result.episode.fallback_count == 1
    assert result.unknown_utterance is not None
    assert result.unknown_utterance.reason == "missing_mandatory_fields"
    assert len(unknown_repository.list_all()) == 1


def test_orchestrator_ambiguous_request_records_unknown() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="chat",
            items=(MessageItem(type="ambiguous_request", text="Сделай что-нибудь хорошее"),),
        )
    )
    orchestrator, program_service, unknown_repository, _, _, _ = build_orchestrator(classifier)

    result = orchestrator.handle_message(
        build_episode(),
        build_message("Сделай что-нибудь хорошее"),
        build_active_program_version(program_service),
    )

    assert result.unknown_utterance is not None
    assert result.episode.fallback_count == 1
    assert result.unknown_utterance.reason == "ambiguous_request"
    assert len(unknown_repository.list_all()) == 1


def test_second_fallback_uses_second_level_response() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="chat",
            items=(MessageItem(type="ambiguous_request", text="Сделай что-нибудь хорошее"),),
        )
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)

    result = orchestrator.handle_message(
        replace(build_episode(), fallback_count=1),
        build_message("Сделай что-нибудь хорошее"),
        build_active_program_version(program_service),
    )

    assert result.episode.fallback_count == 2
    assert result.assistant_response == (
        "Я снова не смог однозначно понять запрос. Напишите задачу одним коротким предложением."
    )


def test_third_fallback_uses_third_level_response() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="chat",
            items=(MessageItem(type="ambiguous_request", text="Сделай что-нибудь хорошее"),),
        )
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)

    result = orchestrator.handle_message(
        replace(build_episode(), fallback_count=2),
        build_message("Сделай что-нибудь хорошее"),
        build_active_program_version(program_service),
    )

    assert result.episode.fallback_count == 3
    assert result.assistant_response == (
        "Запрос всё ещё неясен. Начните с глагола: проверить, создать, показать или отменить."
    )


def test_unknown_utterance_uses_incremented_fallback_count() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="chat",
            items=(MessageItem(type="ambiguous_request", text="Сделай что-нибудь хорошее"),),
        )
    )
    orchestrator, program_service, unknown_repository, _, _, _ = build_orchestrator(classifier)

    result = orchestrator.handle_message(
        replace(build_episode(), fallback_count=1),
        build_message("Сделай что-нибудь хорошее"),
        build_active_program_version(program_service),
    )

    assert result.unknown_utterance is not None
    assert result.unknown_utterance.fallback_count == 2
    assert unknown_repository.list_all()[0].fallback_count == 2


def test_orchestrator_pending_switch_requested_for_new_task_during_pending_rule() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    orchestrator, program_service, _, deferred_repository, _, _ = build_orchestrator(classifier)

    result = orchestrator.handle_message(
        build_episode("pending_rule_review"),
        build_message("Проверить код"),
        build_active_program_version(program_service),
    )

    assert result.pending_switch_decision is not None
    assert result.episode.state == "pending_switch_confirmation"
    assert result.episode.fallback_count == 0
    assert deferred_repository.get_by_episode_id("e1") is not None


def test_orchestrator_rule_candidate_returns_pending_review_without_program_mutation() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
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
    orchestrator, program_service, _, _, rule_candidate_repository, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)

    result = orchestrator.handle_message(
        build_episode(),
        build_message("Показывай понимание"),
        active_version,
    )

    assert result.rule_candidate is not None
    assert result.episode.state == "pending_rule_review"
    assert result.episode.fallback_count == 0
    assert active_version.program.rules == ()
    assert rule_candidate_repository.get_by_episode_id("e1") == result.rule_candidate


def test_rule_candidate_resets_fallback_count() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
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
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)

    result = orchestrator.handle_message(
        replace(build_episode(), fallback_count=2),
        build_message("Показывай понимание"),
        active_version,
    )

    assert result.episode.fallback_count == 0


def test_orchestrator_query_returns_program_contract() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(message_id="m1", primary_intent="query", items=())
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)

    result = orchestrator.handle_message(
        build_episode(),
        build_message("Какие правила активны?"),
        active_version,
    )

    assert result.runtime_result is None
    assert result.episode.fallback_count == 0
    assert result.program_version == active_version
    assert "Активная версия программы" in result.assistant_response


def test_successful_query_resets_fallback_count() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(message_id="m1", primary_intent="query", items=())
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)

    result = orchestrator.handle_message(
        replace(build_episode(), fallback_count=2),
        build_message("Какие правила активны?"),
        active_version,
    )

    assert result.episode.fallback_count == 0


def test_orchestrator_task_executes_runtime_stub() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)

    result = orchestrator.handle_message(
        build_episode(),
        build_message("Проверить код"),
        build_active_program_version(program_service),
    )

    assert result.runtime_result is not None
    assert result.episode.fallback_count == 0
    assert result.runtime_result.status == "completed"


def test_successful_task_resets_fallback_count() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)

    result = orchestrator.handle_message(
        replace(build_episode(), fallback_count=2),
        build_message("Проверить код"),
        build_active_program_version(program_service),
    )

    assert result.runtime_result is not None
    assert result.episode.fallback_count == 0


def test_orchestrator_task_with_active_show_understanding_rule_includes_rule_step() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    candidate = program_service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    patched_version = program_service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )

    result = orchestrator.handle_message(
        build_episode(),
        build_message("Проверить код"),
        patched_version,
    )

    assert result.runtime_result is None
    assert result.episode.state == "pending_understanding_review"
    assert result.episode.fallback_count == 0
    assert "Проверить код" in result.assistant_response


def test_orchestrator_chat_returns_chat_response_without_runtime() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(message_id="m1", primary_intent="chat", items=())
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)

    result = orchestrator.handle_message(
        build_episode(),
        build_message("Как думаешь, получится?"),
        build_active_program_version(program_service),
    )

    assert result.runtime_result is None
    assert result.episode.fallback_count == 0
    assert "Понял" in result.assistant_response


def test_successful_chat_resets_fallback_count() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(message_id="m1", primary_intent="chat", items=())
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)

    result = orchestrator.handle_message(
        replace(build_episode(), fallback_count=2),
        build_message("Как думаешь, получится?"),
        build_active_program_version(program_service),
    )

    assert result.episode.fallback_count == 0


def test_orchestrator_feedback_acknowledged_without_runtime() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="feedback",
            items=(MessageItem(type="feedback", text="Хорошо"),),
        )
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)

    result = orchestrator.handle_message(
        build_episode(),
        build_message("Хорошо"),
        build_active_program_version(program_service),
    )

    assert result.runtime_result is None
    assert "Спасибо" in result.assistant_response


def test_orchestrator_correction_acknowledged_without_runtime() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="correction",
            items=(MessageItem(type="correction", text="Не это имел в виду"),),
        )
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)

    result = orchestrator.handle_message(
        build_episode(),
        build_message("Не это имел в виду"),
        build_active_program_version(program_service),
    )

    assert result.runtime_result is None
    assert "Понял исправление" in result.assistant_response


def test_orchestrator_reject_switch_uses_stored_previous_state() -> None:
    classifier = TrackingClassifier(
        IntakeResult(message_id="m1", primary_intent="query", items=())
    )
    orchestrator, program_service, _, deferred_repository, _, _ = build_orchestrator(classifier)
    deferred_repository.save(
        PendingSwitchService(deferred_repository).request_switch(
            build_episode("pending_understanding_review"),
            build_message("Новая тема", message_id="m2"),
            IntakeResult(message_id="m2", primary_intent="chat", items=()),
            deferred_id="d1",
            created_at=datetime.now(UTC),
        ).deferred_message
    )

    result = orchestrator.handle_message(
        build_episode("pending_switch_confirmation"),
        build_message("нет"),
        build_active_program_version(program_service),
    )

    assert classifier.calls == 0
    assert result.pending_switch_decision is not None
    assert result.episode.state == "pending_understanding_review"


def test_orchestrator_has_no_unused_repository_dependencies() -> None:
    parameters = inspect.signature(Orchestrator.__init__).parameters

    assert "program_version_repository" not in parameters
    assert "deferred_message_repository" not in parameters


def test_confirm_in_pending_rule_review_creates_new_program_version() -> None:
    classifier = TrackingClassifier(
        IntakeResult(message_id="m1", primary_intent="chat", items=())
    )
    orchestrator, program_service, _, _, rule_candidate_repository, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    candidate = program_service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    rule_candidate_repository.save(candidate)

    result = orchestrator.handle_message(
        build_episode("pending_rule_review"),
        build_message("да"),
        active_version,
    )

    assert classifier.calls == 0
    assert result.program_version is not None
    assert result.program_version.version_number == 2


def test_confirm_in_pending_rule_review_sets_episode_open() -> None:
    classifier = TrackingClassifier(
        IntakeResult(message_id="m1", primary_intent="chat", items=())
    )
    orchestrator, program_service, _, _, rule_candidate_repository, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    rule_candidate_repository.save(
        program_service.create_rule_candidate(
            candidate_id="c1",
            source_message_id="m0",
            source_episode_id="e1",
            text="Показывай понимание",
            key="show_understanding_before_execution",
            scope="all_tasks",
        )
    )

    result = orchestrator.handle_message(build_episode("pending_rule_review"), build_message("да"), active_version)

    assert result.episode.state == "open"


def test_confirm_in_pending_rule_review_deletes_pending_candidate() -> None:
    classifier = TrackingClassifier(
        IntakeResult(message_id="m1", primary_intent="chat", items=())
    )
    orchestrator, program_service, _, _, rule_candidate_repository, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    rule_candidate_repository.save(
        program_service.create_rule_candidate(
            candidate_id="c1",
            source_message_id="m0",
            source_episode_id="e1",
            text="Показывай понимание",
            key="show_understanding_before_execution",
            scope="all_tasks",
        )
    )

    orchestrator.handle_message(build_episode("pending_rule_review"), build_message("да"), active_version)

    assert rule_candidate_repository.get_by_episode_id("e1") is None


def test_confirm_enforceable_rule_patches_program_policy() -> None:
    classifier = TrackingClassifier(
        IntakeResult(message_id="m1", primary_intent="chat", items=())
    )
    orchestrator, program_service, _, _, rule_candidate_repository, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    rule_candidate_repository.save(
        program_service.create_rule_candidate(
            candidate_id="c1",
            source_message_id="m0",
            source_episode_id="e1",
            text="Показывай понимание",
            key="show_understanding_before_execution",
            scope="all_tasks",
        )
    )

    result = orchestrator.handle_message(build_episode("pending_rule_review"), build_message("да"), active_version)

    assert result.program_version is not None
    assert result.program_version.program.communication_policy.show_understanding_before_execution is True


def test_reject_in_pending_rule_review_does_not_create_program_version() -> None:
    classifier = TrackingClassifier(
        IntakeResult(message_id="m1", primary_intent="chat", items=())
    )
    orchestrator, program_service, _, _, rule_candidate_repository, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    rule_candidate_repository.save(
        program_service.create_rule_candidate(
            candidate_id="c1",
            source_message_id="m0",
            source_episode_id="e1",
            text="Показывай понимание",
            key="show_understanding_before_execution",
            scope="all_tasks",
        )
    )

    result = orchestrator.handle_message(build_episode("pending_rule_review"), build_message("нет"), active_version)

    assert result.program_version == active_version


def test_reject_in_pending_rule_review_sets_episode_open() -> None:
    classifier = TrackingClassifier(
        IntakeResult(message_id="m1", primary_intent="chat", items=())
    )
    orchestrator, program_service, _, _, rule_candidate_repository, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    rule_candidate_repository.save(
        program_service.create_rule_candidate(
            candidate_id="c1",
            source_message_id="m0",
            source_episode_id="e1",
            text="Показывай понимание",
            key="show_understanding_before_execution",
            scope="all_tasks",
        )
    )

    result = orchestrator.handle_message(build_episode("pending_rule_review"), build_message("нет"), active_version)

    assert result.episode.state == "open"


def test_reject_in_pending_rule_review_deletes_pending_candidate() -> None:
    classifier = TrackingClassifier(
        IntakeResult(message_id="m1", primary_intent="chat", items=())
    )
    orchestrator, program_service, _, _, rule_candidate_repository, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    rule_candidate_repository.save(
        program_service.create_rule_candidate(
            candidate_id="c1",
            source_message_id="m0",
            source_episode_id="e1",
            text="Показывай понимание",
            key="show_understanding_before_execution",
            scope="all_tasks",
        )
    )

    orchestrator.handle_message(build_episode("pending_rule_review"), build_message("нет"), active_version)

    assert rule_candidate_repository.get_by_episode_id("e1") is None


def test_da_and_net_have_different_results_in_pending_rule_review() -> None:
    classifier = TrackingClassifier(
        IntakeResult(message_id="m1", primary_intent="chat", items=())
    )
    orchestrator, program_service, _, _, rule_candidate_repository, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)

    confirm_candidate = program_service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    rule_candidate_repository.save(confirm_candidate)
    confirm_result = orchestrator.handle_message(
        build_episode("pending_rule_review"),
        build_message("да"),
        active_version,
    )

    reject_candidate = program_service.create_rule_candidate(
        candidate_id="c2",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    rule_candidate_repository.save(reject_candidate)
    reject_result = orchestrator.handle_message(
        build_episode("pending_rule_review"),
        build_message("нет"),
        active_version,
    )

    assert confirm_result.assistant_response != reject_result.assistant_response
    assert confirm_result.program_version is not None
    assert confirm_result.program_version.version_number == 2
    assert reject_result.program_version == active_version


def test_confirm_without_pending_candidate_returns_safe_response() -> None:
    classifier = TrackingClassifier(
        IntakeResult(message_id="m1", primary_intent="chat", items=())
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)

    result = orchestrator.handle_message(
        build_episode("pending_rule_review"),
        build_message("да"),
        active_version,
    )

    assert result.episode.state == "open"
    assert "не нашёл" in result.assistant_response.lower()


def test_task_executes_immediately_when_show_understanding_rule_inactive() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    orchestrator, program_service, _, _, _, pending_repository = build_orchestrator(classifier)

    result = orchestrator.handle_message(
        build_episode(),
        build_message("/task Проверить код"),
        build_active_program_version(program_service),
    )

    assert result.runtime_result is not None
    assert result.episode.state == "open"
    assert pending_repository.get_by_episode_id("e1") is None
    assert result.runtime_result.execution_mode == "stub"
    assert result.runtime_result.did_execute_real_work is False
    assert "stub-результат" in result.assistant_response


def test_orchestrator_task_response_does_not_claim_real_execution() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)

    result = orchestrator.handle_message(
        build_episode(),
        build_message("/task Проверить код"),
        build_active_program_version(program_service),
    )

    assert result.runtime_result is not None
    assert "stub-результат" in result.assistant_response
    assert "реальное выполнение задачи не запускалось" in result.assistant_response


def test_task_with_show_understanding_rule_creates_pending_understanding() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    orchestrator, program_service, _, _, _, pending_repository = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    candidate = program_service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    patched_version = program_service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )

    result = orchestrator.handle_message(
        build_episode(),
        build_message("/task Проверить код"),
        patched_version,
    )

    assert result.episode.state == "pending_understanding_review"
    assert result.episode.fallback_count == 0
    assert pending_repository.get_by_episode_id("e1") is not None


def test_pending_understanding_creation_resets_fallback_count() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    orchestrator, program_service, _, _, _, pending_repository = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    candidate = program_service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    patched_version = program_service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )

    result = orchestrator.handle_message(
        replace(build_episode(), fallback_count=2),
        build_message("/task Проверить код"),
        patched_version,
    )

    assert result.episode.state == "pending_understanding_review"
    assert result.episode.fallback_count == 0
    assert pending_repository.get_by_episode_id("e1") is not None


def test_task_with_show_understanding_rule_does_not_execute_immediately() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    candidate = program_service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    patched_version = program_service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )

    result = orchestrator.handle_message(build_episode(), build_message("/task Проверить код"), patched_version)

    assert result.runtime_result is None


def test_pending_understanding_response_contains_understood_task_text() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    candidate = program_service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    patched_version = program_service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )

    result = orchestrator.handle_message(build_episode(), build_message("/task Проверить код"), patched_version)

    assert "Проверить код" in result.assistant_response


def test_confirm_pending_understanding_executes_runtime() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    orchestrator, program_service, _, _, _, pending_repository = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    candidate = program_service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    patched_version = program_service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )
    orchestrator.handle_message(build_episode(), build_message("/task Проверить код"), patched_version)
    assert pending_repository.get_by_episode_id("e1") is not None

    result = orchestrator.handle_message(
        build_episode("pending_understanding_review"),
        build_message("да"),
        patched_version,
    )

    assert result.runtime_result is not None
    assert result.runtime_result.status == "completed"
    assert result.runtime_result.execution_mode == "stub"
    assert result.runtime_result.did_execute_real_work is False


def test_pending_understanding_confirm_returns_stub_honest_runtime_result() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    candidate = program_service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    patched_version = program_service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )
    orchestrator.handle_message(build_episode(), build_message("/task Проверить код"), patched_version)

    result = orchestrator.handle_message(
        build_episode("pending_understanding_review"),
        build_message("да"),
        patched_version,
    )

    assert result.runtime_result is not None
    assert result.runtime_result.execution_mode == "stub"
    assert result.runtime_result.did_execute_real_work is False
    assert "stub-результат" in result.assistant_response


def test_confirm_pending_understanding_runtime_plan_does_not_repeat_show_understanding() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    candidate = program_service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    patched_version = program_service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )
    orchestrator.handle_message(build_episode(), build_message("/task Проверить код"), patched_version)

    result = orchestrator.handle_message(
        build_episode("pending_understanding_review"),
        build_message("да"),
        patched_version,
    )

    assert result.runtime_result is not None
    step_types = tuple(step.type for step in result.runtime_result.runtime_plan.steps)
    assert "show_understanding" not in step_types


def test_confirm_pending_understanding_runtime_plan_executes_and_verifies() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    candidate = program_service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    patched_version = program_service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )
    orchestrator.handle_message(build_episode(), build_message("/task Проверить код"), patched_version)

    result = orchestrator.handle_message(
        build_episode("pending_understanding_review"),
        build_message("да"),
        patched_version,
    )

    assert result.runtime_result is not None
    step_types = tuple(step.type for step in result.runtime_result.runtime_plan.steps)
    assert step_types == ("execute_task_stub", "verify_success_condition")


def test_confirm_pending_understanding_sets_episode_open() -> None:
    classifier = TrackingClassifier(IntakeResult(message_id="m1", primary_intent="chat", items=()))
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    candidate = program_service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    patched_version = program_service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )
    orchestrator.handle_message(build_episode(), build_message("/task Проверить код"), patched_version)

    result = orchestrator.handle_message(build_episode("pending_understanding_review"), build_message("да"), patched_version)

    assert result.episode.state == "open"


def test_confirm_pending_understanding_deletes_pending_record() -> None:
    classifier = TrackingClassifier(IntakeResult(message_id="m1", primary_intent="chat", items=()))
    orchestrator, program_service, _, _, _, pending_repository = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    candidate = program_service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    patched_version = program_service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )
    orchestrator.handle_message(build_episode(), build_message("/task Проверить код"), patched_version)

    orchestrator.handle_message(build_episode("pending_understanding_review"), build_message("да"), patched_version)

    assert pending_repository.get_by_episode_id("e1") is None


def test_reject_pending_understanding_does_not_execute_runtime() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    orchestrator, program_service, _, _, _, pending_repository = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    candidate = program_service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    patched_version = program_service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )
    orchestrator.handle_message(build_episode(), build_message("/task Проверить код"), patched_version)
    assert pending_repository.get_by_episode_id("e1") is not None

    result = orchestrator.handle_message(
        build_episode("pending_understanding_review"),
        build_message("нет"),
        patched_version,
    )

    assert result.runtime_result is None


def test_reject_pending_understanding_sets_episode_open() -> None:
    classifier = TrackingClassifier(IntakeResult(message_id="m1", primary_intent="chat", items=()))
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    candidate = program_service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    patched_version = program_service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )
    orchestrator.handle_message(build_episode(), build_message("/task Проверить код"), patched_version)

    result = orchestrator.handle_message(build_episode("pending_understanding_review"), build_message("нет"), patched_version)

    assert result.episode.state == "open"


def test_reject_pending_understanding_deletes_pending_record() -> None:
    classifier = TrackingClassifier(IntakeResult(message_id="m1", primary_intent="chat", items=()))
    orchestrator, program_service, _, _, _, pending_repository = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    candidate = program_service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m0",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    patched_version = program_service.confirm_rule_candidate(
        active_version=active_version,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )
    orchestrator.handle_message(build_episode(), build_message("/task Проверить код"), patched_version)

    orchestrator.handle_message(build_episode("pending_understanding_review"), build_message("нет"), patched_version)

    assert pending_repository.get_by_episode_id("e1") is None


def test_confirm_without_pending_understanding_returns_safe_response() -> None:
    classifier = TrackingClassifier(IntakeResult(message_id="m1", primary_intent="chat", items=()))
    orchestrator, program_service, _, _, _, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)

    result = orchestrator.handle_message(
        build_episode("pending_understanding_review"),
        build_message("да"),
        active_version,
    )

    assert result.episode.state == "open"
    assert "не нашёл" in result.assistant_response.lower()


def test_cancel_clears_pending_rule_candidate() -> None:
    classifier = TrackingClassifier(IntakeResult(message_id="m1", primary_intent="chat", items=()))
    orchestrator, program_service, _, _, rule_candidate_repository, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    rule_candidate_repository.save(
        program_service.create_rule_candidate(
            candidate_id="c1",
            source_message_id="m0",
            source_episode_id="e1",
            text="Показывай понимание",
            key="show_understanding_before_execution",
            scope="all_tasks",
        )
    )

    result = orchestrator.handle_message(build_episode("pending_rule_review"), build_message("отмена"), active_version)

    assert result.episode.state == "cancelled"
    assert rule_candidate_repository.get_by_episode_id("e1") is None


def test_cancel_clears_pending_understanding() -> None:
    classifier = TrackingClassifier(IntakeResult(message_id="m1", primary_intent="chat", items=()))
    orchestrator, program_service, _, _, _, pending_repository = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    pending_repository.save(
        PendingUnderstanding(
            id="p1",
            episode_id="e1",
            message_id="m1",
            task=RuntimeTask(id="m1", goal="Проверить код"),
            intake_result=IntakeResult(
                message_id="m1",
                primary_intent="task",
                items=(MessageItem(type="task", text="Проверить код"),),
            ),
            created_at=datetime.now(UTC),
        )
    )

    result = orchestrator.handle_message(
        build_episode("pending_understanding_review"),
        build_message("отмена"),
        active_version,
    )

    assert result.episode.state == "cancelled"
    assert pending_repository.get_by_episode_id("e1") is None


def test_cancel_clears_deferred_message() -> None:
    classifier = TrackingClassifier(IntakeResult(message_id="m1", primary_intent="chat", items=()))
    orchestrator, program_service, _, deferred_repository, _, _ = build_orchestrator(classifier)
    active_version = build_active_program_version(program_service)
    deferred_repository.save(
        PendingSwitchService(deferred_repository).request_switch(
            build_episode("pending_rule_review"),
            build_message("Новая тема", message_id="m2"),
            IntakeResult(message_id="m2", primary_intent="chat", items=()),
            deferred_id="d1",
            created_at=datetime.now(UTC),
        ).deferred_message
    )

    result = orchestrator.handle_message(
        build_episode("pending_switch_confirmation"),
        build_message("отмена"),
        active_version,
    )

    assert result.episode.state == "cancelled"
    assert deferred_repository.get_by_episode_id("e1") is None


def test_orchestrator_does_not_use_llm_or_keyword_router() -> None:
    with open("src/jeeves_dap/services/orchestrator.py", encoding="utf-8") as file:
        source = file.read()

    assert "LLMClassifier" not in source
    assert "KeywordClassifier" not in source


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


def test_no_type_ignore() -> None:
    marker = "type" + ": ignore"
    for path in Path("src").rglob("*.py"):
        assert marker not in path.read_text(encoding="utf-8")
    for path in Path("tests").rglob("*.py"):
        assert marker not in path.read_text(encoding="utf-8")


def test_no_mojibake() -> None:
    forbidden = ("\u03a9", "\u00b5", "\u00e6", "\u00c7", "\u221e")
    for path in Path("src").rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert not any(marker in content for marker in forbidden)
