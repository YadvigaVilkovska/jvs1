# Implementation Roadmap — Jeeves DAP

Version: 1.1.1

## Phase 0 — Freeze decisions

Fixed:

```text
no mixed
no semantic deterministic router
exact short command pre-processing only
LLM semantic classification
mandatory field check
item-level validation
ambiguous_request
future_rule for unsupported rules
pending switch confirmation
optional quick replies
fallback escalation
side effects disabled
```

## Phase 1 — Data foundation

Implement:

```text
UserMessage
Episode
DeferredMessage
IntakeResult
MessageItem
RuleCandidate
AgentRule
AgentProgramVersion
EvidenceEvent
UnknownUtterance
```

Acceptance:

```text
Agent Program v1 can be created.
Versions are immutable.
UnknownUtterance can be stored.
DeferredMessage can be stored.
```

## Phase 2 — DeterministicPreProcessor

Implement exact short command handling.

Acceptance:

```text
"Нет." triggers reject in pending state.
"Так, подожди, нет" does not trigger deterministic reject.
"Да, но..." goes to LLM.
```

## Phase 3 — IntentClassifier contract

Implement:

```text
IntentClassifier interface
StubClassifier for tests
LLMClassifier schema placeholder
```

Acceptance:

```text
All tests can run with StubClassifier.
Production path expects LLMClassifier.
No keyword semantic router exists.
```

## Phase 4 — Mandatory and item-level validation

Implement:

```text
mandatory fields by intent
validate_item()
ambiguous_request handling
future_rule assignment for unknown rule keys
review flag derivation
```

Acceptance:

```text
vague task does not execute.
task + unsupported rule is decomposed correctly.
unsupported rule is marked future_rule.
requires_user_review and needs_clarification are never true at the same time.
```

## Phase 5 — ProgramService

Implement:

```text
create rule candidate
confirm enforceable rule
confirm future rule
reject candidate
create Agent Program vN+1
query active program
```

Acceptance:

```text
enforced rules and future rules are separated.
unsupported rule never appears as enforced.
```

## Phase 6 — Pending switch confirmation

Implement:

```text
pending_switch_confirmation state
DeferredMessage
confirm switch
reject switch
cancel
```

Acceptance:

```text
new message during pending review does not silently cancel old state.
```

## Phase 7 — RuleEngine and TaskRuntimeStub

Implement:

```text
show_understanding_before_execution
baseline verification step from verification_policy
TaskRuntimeStub
VerifierStub
```

Acceptance:

```text
active enforceable rule changes runtime plan.
future rules do not change runtime plan.
verification step remains enabled by default without requiring a user rule.
```

## Phase 8 — Fallback escalation and unknown utterances

Implement:

```text
fallback_count
fallback escalation texts
unknown_utterance reasons
LLM invalid schema fallback
missing mandatory fields fallback
```

Acceptance:

```text
repeated fallback does not repeat identical text.
unknown utterances are stored.
```

## Phase 9 — Query active program

Implement query handler.

Must include:

```text
active version
enforced rules
future rules
pending candidates
policies
```

## Phase 10 — E2E vertical slice

Scenario:

```text
User creates enforceable rule.
User confirms.
Agent Program v2 created.
User gives task.
RuleEngine requires understanding review.
User confirms.
TaskRuntimeStub executes.
VerifierStub verifies.
User asks active rules.
System shows enforced rules.

User creates unsupported rule.
System says it is future_rule only.
User confirms.
Query shows it under future rules, not enforced.

User sends vague task.
System asks clarification and logs unknown_utterance.

User starts a new topic during pending review.
System asks switch confirmation.
```

## Phase 11 — v1.2 candidates

Do not implement before v1.1.1 is green:

```text
semantic rule enforcement through LLM
side-effect approval flow
smarter success_condition extraction
detailed correction counters and auto-cancel thresholds
undo one step
memory integration
tool permissions
UI quick reply chips
evaluation dashboard
```
