"""Contract: public package surface for the Jeeves DAP MVP data foundation."""

from jeeves_dap.api import app, create_app
from jeeves_dap.domain.agent_program import (
    KNOWN_RULE_KEYS,
    build_default_agent_program_v1,
)
from jeeves_dap.domain.models import (
    AgentProgram,
    AgentProgramVersion,
    AgentRule,
    DeferredMessage,
    Episode,
    EvidenceEvent,
    IntakeResult,
    MessageItem,
    ModelRoute,
    ModelRoutePair,
    ModelRoutingConfig,
    PendingUnderstanding,
    PendingSwitchDecision,
    QueryProgramContract,
    ReviewFlags,
    RuntimePlan,
    RuntimeResult,
    RuntimeStep,
    RuntimeTask,
    RuleCandidate,
    UnknownUtterance,
    UserMessage,
    VerificationResult,
)
from jeeves_dap.domain.validation import (
    ItemValidationResult,
    compute_understanding_sufficiency,
    derive_rule_application_mode,
    derive_review_flags,
    validate_item,
)
from jeeves_dap.repositories.agent_program_repository import (
    AgentProgramVersionRepository,
    InMemoryAgentProgramVersionRepository,
)
from jeeves_dap.repositories.deferred_message_repository import (
    DeferredMessageRepository,
    InMemoryDeferredMessageRepository,
)
from jeeves_dap.repositories.episode_repository import (
    EpisodeRepository,
    InMemoryEpisodeRepository,
)
from jeeves_dap.repositories.pending_understanding_repository import (
    InMemoryPendingUnderstandingRepository,
    PendingUnderstandingRepository,
)
from jeeves_dap.repositories.rule_candidate_repository import (
    InMemoryRuleCandidateRepository,
    RuleCandidateRepository,
)
from jeeves_dap.repositories.unknown_utterance_repository import (
    InMemoryUnknownUtteranceRepository,
    UnknownUtteranceRepository,
    record_unknown_for_fallback,
)
from jeeves_dap.repositories.user_message_repository import (
    InMemoryUserMessageRepository,
    UserMessageRepository,
)
from jeeves_dap.services.agent_program_service import AgentProgramService
from jeeves_dap.services.classification import (
    DevCommandClassifier,
    IntentClassifier,
    LLMIntakeClassifier,
    LLMIntakeClient,
    StubClassifier,
    StubLLMIntakeClient,
)
from jeeves_dap.services.deterministic_preprocessor import (
    CANCEL_COMMANDS,
    CONFIRM_COMMANDS,
    REJECT_COMMANDS,
    DeterministicPreProcessor,
    PreprocessResult,
)
from jeeves_dap.services.model_routing import (
    ModelRouter,
    build_default_model_routing_config,
    build_model_routing_config_from_env,
)
from jeeves_dap.services.pending_switch_service import PendingSwitchService
from jeeves_dap.services.orchestrator import Orchestrator, OrchestratorTurnResult
from jeeves_dap.services.rule_engine import RuleEngine
from jeeves_dap.services.task_runtime_stub import TaskRuntimeStub
from jeeves_dap.services.verifier_stub import VerifierStub

__all__ = [
    "AgentProgram",
    "AgentProgramService",
    "AgentProgramVersion",
    "AgentProgramVersionRepository",
    "AgentRule",
    "DeferredMessage",
    "DeferredMessageRepository",
    "DevCommandClassifier",
    "DeterministicPreProcessor",
    "Episode",
    "EpisodeRepository",
    "EvidenceEvent",
    "InMemoryDeferredMessageRepository",
    "InMemoryAgentProgramVersionRepository",
    "InMemoryEpisodeRepository",
    "InMemoryPendingUnderstandingRepository",
    "InMemoryRuleCandidateRepository",
    "InMemoryUnknownUtteranceRepository",
    "InMemoryUserMessageRepository",
    "IntakeResult",
    "IntentClassifier",
    "ItemValidationResult",
    "KNOWN_RULE_KEYS",
    "LLMIntakeClassifier",
    "LLMIntakeClient",
    "MessageItem",
    "ModelRoute",
    "ModelRoutePair",
    "ModelRouter",
    "ModelRoutingConfig",
    "Orchestrator",
    "OrchestratorTurnResult",
    "PendingUnderstanding",
    "PendingUnderstandingRepository",
    "PendingSwitchDecision",
    "PendingSwitchService",
    "PreprocessResult",
    "QueryProgramContract",
    "StubClassifier",
    "StubLLMIntakeClient",
    "ReviewFlags",
    "RuleCandidateRepository",
    "RuleEngine",
    "RuntimePlan",
    "RuntimeResult",
    "RuntimeStep",
    "RuntimeTask",
    "RuleCandidate",
    "TaskRuntimeStub",
    "UnknownUtteranceRepository",
    "UnknownUtterance",
    "UserMessage",
    "UserMessageRepository",
    "VerificationResult",
    "VerifierStub",
    "app",
    "build_default_agent_program_v1",
    "build_default_model_routing_config",
    "build_model_routing_config_from_env",
    "CANCEL_COMMANDS",
    "CONFIRM_COMMANDS",
    "compute_understanding_sufficiency",
    "create_app",
    "derive_rule_application_mode",
    "derive_review_flags",
    "REJECT_COMMANDS",
    "record_unknown_for_fallback",
    "validate_item",
]
