# Architecture Plan — Jeeves DAP

Version: 1.1.1

## 1. Architecture goal

Build a minimal, inspectable architecture where the agent's behavior is controlled by a versioned Agent Program formed through dialogue.

The architecture must avoid:

```text
hidden prompt-only behavior
fake active rules
silent pending cancellation
keyword semantic routing
unbounded execution side effects
```

## 2. Executable MVP modules

```text
ChatOrchestrator
DeterministicPreProcessor
IntentClassifier
ProgramService
RuleEngine
EvidenceService
UnknownUtteranceService
TaskRuntimeStub
VerifierStub
```

## 3. Runtime architecture

```text
Client / Chat UI
↓
Chat API
↓
ChatOrchestrator
↓
DeterministicPreProcessor
  only exact yes/no/cancel
↓
IntentClassifier
  LLMClassifier in production
  StubClassifier in tests
↓
Schema validation
↓
Mandatory field check
↓
Item-level validation
↓
Flow decision
↓
ProgramService
↓
RuleEngine
↓
TaskRuntimeStub
↓
VerifierStub
↓
EvidenceService
↓
UnknownUtteranceService where needed
```

## 4. Component responsibilities

### 4.1 ChatOrchestrator

Responsible for:

1. receiving user message;
2. loading episode;
3. deriving state;
4. running DeterministicPreProcessor;
5. calling IntentClassifier when needed;
6. validating schema;
7. computing sufficiency;
8. validating actionable items;
9. detecting pending switch conflict;
10. routing to handler;
11. returning assistant response.

### 4.2 DeterministicPreProcessor

Only recognizes exact short commands:

```text
confirm
reject
cancel
```

It must not classify tasks, rules, feedback, query or chat.

### 4.3 IntentClassifier

```python
class IntentClassifier(ABC):
    def classify(self, text: str, episode_state: EpisodeState) -> IntakeResult:
        ...
```

Implementations:

```text
LLMClassifier  → production
StubClassifier → tests only
```

### 4.4 ProgramService

Responsible for:

1. Agent Program v1 creation;
2. immutable versioning;
3. rule candidate creation;
4. known key mapping;
5. unsupported / future rule handling;
6. conflict detection;
7. rule confirmation / rejection;
8. query formatting.

### 4.5 RuleEngine

Responsible for:

1. applying enforceable known keys;
2. adding baseline verification step from `verification_policy`;
3. building inspectable runtime plans.

MVP keys:

```text
show_understanding_before_execution
```

### 4.6 EvidenceService

Records all important state changes.

### 4.7 UnknownUtteranceService

Records unclear or unsupported utterances for later analysis.

## 5. Episode states

```text
open
pending_understanding_review
pending_rule_review
pending_switch_confirmation
executing
completed
cancelled
```

`cached_state` is cache only. Source of truth is `derive_episode_state()`.

## 6. Pending switch flow

```text
pending_understanding_review / pending_rule_review
↓
new unrelated semantic message
↓
pending_switch_confirmation
↓
ask user whether to cancel pending object and process new message
```

Use `DeferredMessage` to preserve the new message until the user confirms.

## 7. Rule lifecycle

For enforceable rules:

```text
candidate → active → revoked
```

For unsupported rules:

```text
candidate → future → revoked
```

Important:

```text
future != active enforced
```

## 8. Rule key registry

```python
KNOWN_RULE_KEYS = {
    "show_understanding_before_execution": {
        "application_mode": "enforced_by_rule_engine",
        "policy_patch": {
            "communication_policy.show_understanding_before_execution": True
        },
    },
}
```

Unknown key:

```text
application_mode = future_rule
status after confirmation = future
```

## 9. Database tables

Minimum:

```text
messages
episodes
deferred_messages
normalized_understandings
rule_candidates
agent_programs
agent_program_versions
evidence_events
unknown_utterances
```

## 10. Engineering acceptance

Implementation is accepted only if:

```text
no mixed
no semantic deterministic routing
exact short command matching only
vague task does not execute
unsupported rules are marked future
pending switch does not silently cancel old state
quick replies are optional only
fallback escalation works
query shows enforced vs future rules separately
```
