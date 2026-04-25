"""Contract: service-level orchestration vertical slice using existing pure services and stubs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

from jeeves_dap.domain.models import (
    AgentProgramVersion,
    Episode,
    IntakeResult,
    PendingUnderstanding,
    PendingSwitchDecision,
    RuleCandidate,
    RuntimeResult,
    RuntimeTask,
    UnknownUtterance,
    UserMessage,
)
from jeeves_dap.domain.validation import compute_understanding_sufficiency, derive_review_flags
from jeeves_dap.repositories.pending_understanding_repository import PendingUnderstandingRepository
from jeeves_dap.repositories.rule_candidate_repository import RuleCandidateRepository
from jeeves_dap.repositories.unknown_utterance_repository import (
    UnknownUtteranceRepository,
    record_unknown_for_fallback,
)
from jeeves_dap.services.agent_program_service import AgentProgramService
from jeeves_dap.services.classification import IntentClassifier
from jeeves_dap.services.deterministic_preprocessor import DeterministicPreProcessor
from jeeves_dap.services.pending_switch_service import PendingSwitchService
from jeeves_dap.services.task_runtime_stub import TaskRuntimeStub

CHAT_RESPONSE_TEXT = "Понял. Можем обсудить это подробнее."
FEEDBACK_RESPONSE_TEXT = "Спасибо за обратную связь."
CORRECTION_RESPONSE_TEXT = "Понял исправление."
PENDING_RULE_RESPONSE_TEMPLATE = (
    "Я понял это как правило: {text}. "
    "Сохранить и рассмотреть его как ожидающее подтверждения?"
)
QUERY_RESPONSE_TEMPLATE = "Активная версия программы: {active_version}."
CANCEL_RESPONSE_TEXT = "Эпизод отменён."
RULE_CONFIRMED_RESPONSE_TEXT = "Правило подтверждено и сохранено."
RULE_REJECTED_RESPONSE_TEXT = "Правило отклонено и не сохранено."
MISSING_PENDING_RULE_RESPONSE_TEXT = "Не нашёл ожидающее подтверждения правило. Опишите правило заново."
PENDING_UNDERSTANDING_RESPONSE_TEMPLATE = (
    'Я понял задачу так: "{task_text}". Подтвердите текстом "да" или отклоните текстом "нет".'
)
UNDERSTANDING_REJECTED_RESPONSE_TEXT = "Понял, не выполняю. Сформулируйте задачу заново."
MISSING_PENDING_UNDERSTANDING_RESPONSE_TEXT = "Не нашёл ожидающее подтверждения понимание задачи. Опишите задачу заново."


@dataclass(frozen=True, slots=True)
class OrchestratorTurnResult:
    """Contract: one orchestrated turn result across pre-processing, validation, and stub execution."""

    episode: Episode
    assistant_response: str
    intake_result: IntakeResult | None = None
    runtime_result: RuntimeResult | None = None
    program_version: AgentProgramVersion | None = None
    rule_candidate: RuleCandidate | None = None
    pending_switch_decision: PendingSwitchDecision | None = None
    unknown_utterance: UnknownUtterance | None = None


class Orchestrator:
    """Contract: minimal vertical slice that wires existing services without UI or LLM impls."""

    def __init__(
        self,
        *,
        classifier: IntentClassifier,
        preprocessor: DeterministicPreProcessor,
        program_service: AgentProgramService,
        rule_candidate_repository: RuleCandidateRepository,
        pending_understanding_repository: PendingUnderstandingRepository,
        unknown_utterance_repository: UnknownUtteranceRepository,
        pending_switch_service: PendingSwitchService,
        task_runtime: TaskRuntimeStub,
    ) -> None:
        self._classifier = classifier
        self._preprocessor = preprocessor
        self._program_service = program_service
        self._rule_candidate_repository = rule_candidate_repository
        self._pending_understanding_repository = pending_understanding_repository
        self._unknown_utterance_repository = unknown_utterance_repository
        self._pending_switch_service = pending_switch_service
        self._task_runtime = task_runtime

    def handle_message(
        self,
        episode: Episode,
        user_message: UserMessage,
        active_program_version: AgentProgramVersion,
    ) -> OrchestratorTurnResult:
        """Handle one user message through deterministic control flow and stubbed services."""

        preprocess_result = self._preprocessor.preprocess(user_message.text, episode.state)
        if preprocess_result is not None:
            if preprocess_result.action == "cancel":
                self._rule_candidate_repository.delete_by_episode_id(episode.id)
                self._pending_understanding_repository.delete_by_episode_id(episode.id)
                decision = self._pending_switch_service.cancel_episode(episode)
                return OrchestratorTurnResult(
                    episode=decision.episode,
                    assistant_response=CANCEL_RESPONSE_TEXT,
                    program_version=active_program_version,
                    pending_switch_decision=decision,
                )

            if episode.state == "pending_understanding_review":
                pending_understanding = self._pending_understanding_repository.get_by_episode_id(episode.id)
                if pending_understanding is None:
                    return OrchestratorTurnResult(
                        episode=replace(episode, state="open"),
                        assistant_response=MISSING_PENDING_UNDERSTANDING_RESPONSE_TEXT,
                        program_version=active_program_version,
                    )

                if preprocess_result.action == "confirm":
                    runtime_result = self._task_runtime.execute(
                        pending_understanding.task,
                        active_program_version.program,
                        include_show_understanding_step=False,
                    )
                    self._pending_understanding_repository.delete_by_episode_id(episode.id)
                    return OrchestratorTurnResult(
                        episode=replace(episode, state="open"),
                        assistant_response=runtime_result.result_text,
                        intake_result=pending_understanding.intake_result,
                        runtime_result=runtime_result,
                        program_version=active_program_version,
                    )

                if preprocess_result.action == "reject":
                    self._pending_understanding_repository.delete_by_episode_id(episode.id)
                    return OrchestratorTurnResult(
                        episode=replace(episode, state="open"),
                        assistant_response=UNDERSTANDING_REJECTED_RESPONSE_TEXT,
                        intake_result=pending_understanding.intake_result,
                        program_version=active_program_version,
                    )

            if episode.state == "pending_rule_review":
                pending_candidate = self._rule_candidate_repository.get_by_episode_id(episode.id)
                if pending_candidate is None:
                    return OrchestratorTurnResult(
                        episode=replace(episode, state="open"),
                        assistant_response=MISSING_PENDING_RULE_RESPONSE_TEXT,
                        program_version=active_program_version,
                    )

                if preprocess_result.action == "confirm":
                    next_version_id = f"v{active_program_version.version_number + 1}"
                    new_version = self._program_service.confirm_rule_candidate(
                        active_version=active_program_version,
                        candidate=pending_candidate,
                        new_version_id=next_version_id,
                        new_rule_id=str(uuid4()),
                        created_at=datetime.now(UTC),
                    )
                    self._rule_candidate_repository.delete_by_episode_id(episode.id)
                    return OrchestratorTurnResult(
                        episode=replace(episode, state="open"),
                        assistant_response=RULE_CONFIRMED_RESPONSE_TEXT,
                        program_version=new_version,
                        rule_candidate=pending_candidate,
                    )

                if preprocess_result.action == "reject":
                    rejected_candidate = self._program_service.reject_rule_candidate(pending_candidate)
                    self._rule_candidate_repository.delete_by_episode_id(episode.id)
                    return OrchestratorTurnResult(
                        episode=replace(episode, state="open"),
                        assistant_response=RULE_REJECTED_RESPONSE_TEXT,
                        program_version=active_program_version,
                        rule_candidate=rejected_candidate,
                    )

            if episode.state == "pending_switch_confirmation":
                if preprocess_result.action == "confirm":
                    decision = self._pending_switch_service.confirm_switch(episode)
                    return OrchestratorTurnResult(
                        episode=decision.episode,
                        assistant_response=decision.assistant_response,
                        program_version=active_program_version,
                        pending_switch_decision=decision,
                    )
                if preprocess_result.action == "reject":
                    decision = self._pending_switch_service.reject_switch(episode)
                    return OrchestratorTurnResult(
                        episode=decision.episode,
                        assistant_response=decision.assistant_response,
                        program_version=active_program_version,
                        pending_switch_decision=decision,
                    )

        intake_result = self._classifier.classify(user_message.text, episode.state)
        review_flags = derive_review_flags(intake_result)
        sufficient = compute_understanding_sufficiency(intake_result)
        normalized_intake = replace(
            intake_result,
            needs_clarification=review_flags.needs_clarification,
            requires_user_review=review_flags.requires_user_review,
            is_understanding_sufficient=sufficient,
        )

        if review_flags.needs_clarification:
            reason = "ambiguous_request" if any(
                item.type == "ambiguous_request" for item in normalized_intake.items
            ) else "missing_mandatory_fields"
            unknown_utterance = record_unknown_for_fallback(
                self._unknown_utterance_repository,
                episode_id=episode.id,
                message_id=user_message.id,
                utterance_text=user_message.text,
                detected_intent=normalized_intake.primary_intent,
                reason=reason,
                fallback_count=episode.fallback_count + 1,
                context_snapshot={"episode_state": episode.state},
            )
            return OrchestratorTurnResult(
                episode=episode,
                assistant_response="Я не смог однозначно понять запрос. Уточните, что нужно сделать.",
                intake_result=normalized_intake,
                program_version=active_program_version,
                unknown_utterance=unknown_utterance,
            )

        if self._pending_switch_service.should_request_switch(episode, normalized_intake):
            decision = self._pending_switch_service.request_switch(
                episode,
                user_message,
                normalized_intake,
                deferred_id=str(uuid4()),
                created_at=datetime.now(UTC),
            )
            return OrchestratorTurnResult(
                episode=decision.episode,
                assistant_response=decision.assistant_response,
                intake_result=normalized_intake,
                program_version=active_program_version,
                pending_switch_decision=decision,
            )

        rule_item = next((item for item in normalized_intake.items if item.type == "rule_candidate"), None)
        if rule_item is not None:
            rule_candidate = self._program_service.create_rule_candidate(
                candidate_id=str(uuid4()),
                source_message_id=user_message.id,
                source_episode_id=episode.id,
                text=rule_item.text,
                key=rule_item.key,
                scope=rule_item.scope or "all_tasks",
            )
            self._rule_candidate_repository.save(rule_candidate)
            updated_episode = replace(episode, state="pending_rule_review")
            return OrchestratorTurnResult(
                episode=updated_episode,
                assistant_response=(
                    PENDING_RULE_RESPONSE_TEMPLATE.format(text=rule_candidate.text)
                    + ' Подтвердите текстом "да" или отклоните текстом "нет".'
                ),
                intake_result=normalized_intake,
                program_version=active_program_version,
                rule_candidate=rule_candidate,
            )

        if normalized_intake.primary_intent == "query":
            contract = self._program_service.build_query_program_contract(
                active_version=active_program_version,
                pending_candidates=(),
            )
            return OrchestratorTurnResult(
                episode=episode,
                assistant_response=QUERY_RESPONSE_TEMPLATE.format(active_version=contract.active_version),
                intake_result=normalized_intake,
                program_version=active_program_version,
            )

        if normalized_intake.primary_intent == "task" and not normalized_intake.requires_user_review:
            task_item = next(item for item in normalized_intake.items if item.type == "task")
            runtime_task = RuntimeTask(
                id=user_message.id,
                goal=task_item.text,
            )
            if active_program_version.program.communication_policy.show_understanding_before_execution:
                pending_understanding = PendingUnderstanding(
                    id=str(uuid4()),
                    episode_id=episode.id,
                    message_id=user_message.id,
                    task=runtime_task,
                    intake_result=normalized_intake,
                    created_at=datetime.now(UTC),
                )
                self._pending_understanding_repository.save(pending_understanding)
                return OrchestratorTurnResult(
                    episode=replace(episode, state="pending_understanding_review"),
                    assistant_response=PENDING_UNDERSTANDING_RESPONSE_TEMPLATE.format(
                        task_text=runtime_task.goal
                    ),
                    intake_result=normalized_intake,
                    program_version=active_program_version,
                )
            runtime_result = self._task_runtime.execute(runtime_task, active_program_version.program)
            return OrchestratorTurnResult(
                episode=episode,
                assistant_response=runtime_result.result_text,
                intake_result=normalized_intake,
                runtime_result=runtime_result,
                program_version=active_program_version,
            )

        if normalized_intake.primary_intent == "chat":
            return OrchestratorTurnResult(
                episode=episode,
                assistant_response=CHAT_RESPONSE_TEXT,
                intake_result=normalized_intake,
                program_version=active_program_version,
            )

        if normalized_intake.primary_intent == "feedback":
            return OrchestratorTurnResult(
                episode=episode,
                assistant_response=FEEDBACK_RESPONSE_TEXT,
                intake_result=normalized_intake,
                program_version=active_program_version,
            )

        if normalized_intake.primary_intent == "correction":
            return OrchestratorTurnResult(
                episode=episode,
                assistant_response=CORRECTION_RESPONSE_TEXT,
                intake_result=normalized_intake,
                program_version=active_program_version,
            )

        unknown_utterance = record_unknown_for_fallback(
            self._unknown_utterance_repository,
            episode_id=episode.id,
            message_id=user_message.id,
            utterance_text=user_message.text,
            detected_intent=normalized_intake.primary_intent,
            reason="missing_mandatory_fields",
            fallback_count=episode.fallback_count + 1,
            context_snapshot={"episode_state": episode.state},
        )
        return OrchestratorTurnResult(
            episode=episode,
            assistant_response="Я не смог однозначно понять запрос. Уточните, что нужно сделать.",
            intake_result=normalized_intake,
            program_version=active_program_version,
            unknown_utterance=unknown_utterance,
        )
