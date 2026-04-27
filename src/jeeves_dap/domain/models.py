"""Contract: immutable Jeeves DAP domain schemas with MVP-only vocabulary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

PrimaryIntent = Literal[
    "task",
    "rule_update",
    "correction",
    "feedback",
    "query",
    "cancel",
    "chat",
]

MessageItemType = Literal[
    "task",
    "rule_candidate",
    "correction",
    "feedback",
    "query",
    "cancel",
    "ambiguous_request",
]

ApplicationMode = Literal["enforced_by_rule_engine", "future_rule"]
ModelRole = Literal["intake", "work"]
ModelProvider = Literal["openai", "deepseek"]
RuleStatus = Literal["candidate", "active", "future", "revoked"]
RuleReviewState = Literal["pending", "confirmed", "rejected"]
RuleConflictState = Literal["none", "unresolved", "resolved"]
EpisodeState = Literal[
    "open",
    "pending_understanding_review",
    "pending_rule_review",
    "pending_switch_confirmation",
    "executing",
    "completed",
    "cancelled",
]


@dataclass(frozen=True, slots=True)
class UserMessage:
    """Contract: raw text message received from the user for one episode."""

    id: str
    episode_id: str
    text: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Episode:
    """Contract: persistent conversation episode state without runtime side effects."""

    id: str
    user_id: str
    state: EpisodeState = "open"
    fallback_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class DeferredMessage:
    """Contract: stores a new message while pending review waits for user confirmation."""

    id: str
    episode_id: str
    message_id: str
    intake_result: "IntakeResult"
    created_at: datetime
    previous_episode_state: EpisodeState | None = None


@dataclass(frozen=True, slots=True)
class MessageItem:
    """Contract: normalized semantic item extracted from one user message."""

    type: MessageItemType
    text: str
    scope: str | None = None
    key: str | None = None
    application_mode: ApplicationMode | None = None
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class IntakeResult:
    """Contract: top-level semantic parse result produced by a classifier contract."""

    message_id: str
    primary_intent: PrimaryIntent
    items: tuple[MessageItem, ...]
    requires_user_review: bool = False
    fallback_triggered: bool = False
    needs_clarification: bool = False
    is_understanding_sufficient: bool = False


@dataclass(frozen=True, slots=True)
class RuleCandidate:
    """Contract: pending or confirmed rule proposal derived from dialogue."""

    id: str
    source_message_id: str
    source_episode_id: str
    text: str
    key: str | None
    scope: str
    application_mode: ApplicationMode
    status: RuleStatus
    review_state: RuleReviewState
    conflict_state: RuleConflictState
    conflicts_with_rule_id: str | None = None


@dataclass(frozen=True, slots=True)
class AgentRule:
    """Contract: stored rule snapshot inside a versioned agent program."""

    id: str
    text: str
    key: str | None
    scope: str
    status: Literal["active", "future", "revoked"]
    application_mode: ApplicationMode
    source_message_id: str
    source_episode_id: str


@dataclass(frozen=True, slots=True)
class CommunicationPolicy:
    """Contract: immutable communication settings for a program version."""

    show_understanding_before_execution: bool = False


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    """Contract: memory policy remains disabled in MVP while keeping a stable schema."""

    enabled: bool = False
    retention: str = "episode"


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    """Contract: tool policy declares side effects unsupported for MVP."""

    allowed_tools: tuple[str, ...] = ()
    require_approval_for_side_effects: bool = False
    side_effects_supported: bool = False


@dataclass(frozen=True, slots=True)
class VerificationPolicy:
    """Contract: baseline verification policy that is not controlled by rule keys."""

    must_check_success_condition: bool = True
    default_success_condition_mode: str = "completed_status_is_success"


@dataclass(frozen=True, slots=True)
class AgentProgram:
    """Contract: immutable agent program snapshot with policies and stored rules."""

    rules: tuple[AgentRule, ...]
    communication_policy: CommunicationPolicy
    memory_policy: MemoryPolicy
    tool_policy: ToolPolicy
    verification_policy: VerificationPolicy


@dataclass(frozen=True, slots=True)
class AgentProgramVersion:
    """Contract: immutable version wrapper around one full agent program snapshot."""

    id: str
    version_number: int
    program: AgentProgram
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EvidenceEvent:
    """Contract: auditable event record for schema, program, and flow decisions."""

    id: str
    episode_id: str
    message_id: str | None
    event_type: str
    result: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class UnknownUtterance:
    """Contract: stores unclear or unsupported utterances without a separate LLM error table."""

    id: str
    episode_id: str
    message_id: str
    utterance_text: str
    detected_intent: str | None
    reason: str
    fallback_count: int = 1
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    reviewed: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ReviewFlags:
    """Contract: derived control flags used by orchestrators after semantic parsing."""

    requires_user_review: bool
    needs_clarification: bool


@dataclass(frozen=True, slots=True)
class QueryProgramContract:
    """Contract: query payload shape for active program inspection responses."""

    active_version: int
    enforced_rules: tuple[AgentRule, ...] = ()
    future_rules: tuple[AgentRule, ...] = ()
    pending_candidates: tuple[RuleCandidate, ...] = ()
    policies: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelRoute:
    """Contract: one provider/model target for a specific model role route."""

    provider: ModelProvider
    model: str


@dataclass(frozen=True, slots=True)
class ModelRoutePair:
    """Contract: one primary and one fallback route for a model role."""

    primary: ModelRoute
    fallback: ModelRoute


@dataclass(frozen=True, slots=True)
class ModelRoutingConfig:
    """Contract: full routing config for intake and work model roles."""

    intake: ModelRoutePair
    work: ModelRoutePair


@dataclass(frozen=True, slots=True)
class RuntimeTask:
    """Contract: minimal runtime task description used by rule engine and task stub."""

    id: str
    goal: str
    success_condition: str | None = None


@dataclass(frozen=True, slots=True)
class PendingUnderstanding:
    """Contract: stored pending task understanding awaiting explicit user confirmation."""

    id: str
    episode_id: str
    message_id: str
    task: RuntimeTask
    intake_result: IntakeResult
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RuntimeStep:
    """Contract: one inspectable runtime step in the generated plan."""

    type: str
    requires_confirmation: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimePlan:
    """Contract: ordered runtime steps built from task plus active program policies."""

    steps: tuple[RuntimeStep, ...]


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Contract: stub verification outcome and checked success condition."""

    verified: bool
    checked_success_condition: str


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    """Contract: stub runtime result with applied rules, plan, and verification outcome."""

    task_id: str
    status: str
    execution_mode: Literal["stub", "read_only_repo_review"]
    did_execute_real_work: bool
    result_text: str
    applied_rules: tuple[str, ...]
    runtime_plan: RuntimePlan
    verification_result: VerificationResult


@dataclass(frozen=True, slots=True)
class PendingSwitchDecision:
    """Contract: service-level decision for pending switch confirmation flow."""

    action: str
    episode: Episode
    assistant_response: str
    deferred_message: DeferredMessage | None = None
    process_deferred: bool = False
