# Technical Specification — Jeeves DAP MVP

Version: 1.1.1

## 1. Goal

Implement Jeeves DAP MVP as a mechanically correct vertical slice:

```text
text-only protocol
+ exact yes/no/cancel pre-processing
+ LLM semantic classification
+ schema validation
+ mandatory field check
+ item-level validation
+ rule candidate lifecycle
+ Agent Program versioning
+ Rule Engine for known keys
+ TaskRuntimeStub
+ VerifierStub
+ EvidenceEvent
+ UnknownUtterance
```

## 2. Non-goals

Do not implement:

```text
side effects
side-effect approval flow
semantic rule enforcement through LLM
multi-agent orchestration
complex UI
graph memory
automatic rule deletion
production deterministic semantic router
```

## 3. Schemas

### 3.1 IntakeResult

```python
class IntakeResult(BaseModel):
    message_id: str
    primary_intent: Literal[
        "task", "rule_update", "correction", "feedback", "query", "cancel", "chat"
    ]
    items: list[MessageItem]
    # True when assistant is waiting for explicit user confirmation of a prepared object.
    requires_user_review: bool = False
    fallback_triggered: bool = False
    # True when the message is too vague and assistant must ask to clarify the request.
    needs_clarification: bool = False

    # computed by system, not trusted from LLM
    is_understanding_sufficient: bool = False
```

### 3.2 MessageItem

```python
class MessageItem(BaseModel):
    type: Literal[
        "task", "rule_candidate", "correction", "feedback",
        "query", "cancel", "ambiguous_request"
    ]
    text: str
    scope: str | None = None
    key: str | None = None
    application_mode: Literal["enforced_by_rule_engine", "future_rule"] | None = None
    confidence: float | None = None
```

### 3.3 RuleCandidate

```python
class RuleCandidate(BaseModel):
    id: str
    source_message_id: str
    source_episode_id: str
    text: str
    key: str | None
    scope: str
    application_mode: Literal["enforced_by_rule_engine", "future_rule"]
    status: Literal["candidate", "active", "future", "revoked"]
    review_state: Literal["pending", "confirmed", "rejected"]
    conflict_state: Literal["none", "unresolved", "resolved"]
    conflicts_with_rule_id: str | None = None
```

### 3.4 AgentRule

```python
class AgentRule(BaseModel):
    id: str
    text: str
    key: str | None
    scope: str
    status: Literal["active", "future", "revoked"]
    application_mode: Literal["enforced_by_rule_engine", "future_rule"]
    source_message_id: str
    source_episode_id: str
```

## 4. Default Agent Program v1

```json
{
  "rules": [],
  "communication_policy": {"show_understanding_before_execution": false},
  "memory_policy": {"enabled": false, "retention": "episode"},
  "tool_policy": {
    "allowed_tools": [],
    "require_approval_for_side_effects": false,
    "side_effects_supported": false
  },
  "verification_policy": {
    "must_check_success_condition": true,
    "default_success_condition_mode": "completed_status_is_success"
  }
}
```

`must_check_success_condition` is a baseline MVP verification policy, not a user-configurable rule key.

## 5. Intent and items

No `mixed`.

Correct:

```json
{
  "primary_intent": "task",
  "items": [
    {"type": "task", "text": "Проверить код"},
    {"type": "rule_candidate", "text": "Для таких задач сначала писать ожидаемый результат"}
  ]
}
```

## 6. Chat vs vague task

A valid task requires:

```text
action
object / target
expected result or implied deliverable
```

Examples:

```text
"Сделай краткое ТЗ" → task
"Проверь код" → task
"Что такое хорошая погода?" → chat / conversational answer
"Как думаешь, получится?" → chat
"Сделай что-нибудь хорошее" → chat + ambiguous_request + needs_clarification
```

## 7. Mandatory field check

```text
task        → at least one valid task item
rule_update → at least one valid rule_candidate item
correction  → at least one valid correction item
feedback    → at least one valid feedback item
query       → valid primary_intent is enough; query item preferred
cancel      → deterministic cancel command or cancel item
chat        → no mandatory fields
```

Review flags decision table:

```text
requires_user_review = true  → assistant is waiting for explicit confirmation of
                               normalized understanding or rule candidate
needs_clarification = true   → user request is too vague to execute safely

Both flags must not be true at the same time in MVP.

pending_understanding_review / pending_rule_review
    → requires_user_review = true

chat + ambiguous_request
    → needs_clarification = true
```

## 8. Item-level validation

```python
KNOWN_RULE_KEYS = {
    "show_understanding_before_execution",
}

def validate_item(item: MessageItem) -> ItemValidationResult:
    if item.type in {"task", "rule_candidate", "correction", "feedback"}:
        if not item.text or not item.text.strip():
            return invalid("empty_text")

    if item.type == "rule_candidate":
        if not item.scope:
            return invalid("missing_scope")

        if item.key in KNOWN_RULE_KEYS:
            item.application_mode = "enforced_by_rule_engine"
        else:
            item.application_mode = "future_rule"

    if item.type == "ambiguous_request":
        return clarification_required("ambiguous_request")

    return valid()
```

Behavior:

```text
valid task + invalid rule_candidate → do not discard task; ask about invalid rule part
valid task + unsupported rule_candidate → task remains the primary flow; assistant says the task will run under the current program and the unsupported rule can be saved later as future_rule in a separate message
only ambiguous_request → ask clarification; do not execute
no valid actionable items and not chat/query → fallback
```

MVP does not introduce a special deterministic mini-protocol for:

```text
task + unsupported rule in one message
```

The assistant must keep the task as the main flow and must not create a hidden choice state that is controlled by keywords.

## 9. DeterministicPreProcessor

Only exact short commands are recognized before LLM.

```text
confirm: да, верно, подтверждаю, так, сохрани, конечно
reject: нет, не так, не подтверждаю, не сохраняй, не нужно
cancel: отмена, забудь, начнём заново, начать заново, отменить
```

Matching rule:

```text
normalize whitespace
lowercase
strip punctuation at boundaries
exact match only
no substring matching
```

Examples:

```text
"Нет." → reject
"Так, подожди, нет, дай подумать" → not deterministic; send to LLM
"Да, но..." → not deterministic; send to LLM
```

## 10. IntentClassifier

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

Forbidden:

```text
production keyword router for semantic intent classification
```

## 11. Rule key registry

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
not enforced by RuleEngine
```

## 12. Pending switch confirmation

When an unrelated semantic message arrives during pending review:

```python
if episode.state in {"pending_rule_review", "pending_understanding_review"}:
    if incoming_intent in {"task", "query", "rule_update", "chat"} and not is_related_to_pending:
        return ask_pending_switch_confirmation()
```

Response:

```text
У нас осталось неподтверждённое правило/понимание.

Если перейти к новому сообщению или новой теме, оно будет отменено. Отменить его и продолжить с новым сообщением?
```

State:

```text
pending_switch_confirmation
```

Use `DeferredMessage` to store the new message while waiting for confirmation.

## 13. Correction flow

```text
each correction creates a new NormalizedUnderstanding revision
confirmation finalizes the latest revision
detailed correction counters and automatic cancellation are deferred to v1.2
```

## 14. Fallback escalation

Track `fallback_count` per episode.

```python
if fallback_count == 1:
    response = "Я не смог понять запрос. Уточните, что нужно сделать."
elif fallback_count == 2:
    response = "Мне всё ещё неясно. Напишите в формате: “сделай X”, “запомни правило Y” или “отмени”."
else:
    response = "Похоже, сейчас лучше сначала обсудить цель. Что вы хотите получить в результате?"
```

Each fallback records `EvidenceEvent` and `UnknownUtterance`.

## 15. UnknownUtterance table

```sql
CREATE TABLE unknown_utterances (
    id UUID PRIMARY KEY,
    episode_id UUID,
    message_id UUID,
    utterance_text TEXT NOT NULL,
    detected_intent TEXT,
    reason TEXT,
    fallback_count INTEGER DEFAULT 1,
    context_snapshot JSON,
    reviewed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL
);
```

Reasons:

```text
invalid_schema_after_retries
missing_mandatory_fields
ambiguous_request
unsupported_semantic_shape
fallback_escalation
```

## 16. RuleEngine

MVP Rule Engine enforces only known keys.

```python
def build_runtime_plan(task, active_program):
    steps = []

    if active_program.communication_policy.get("show_understanding_before_execution"):
        steps.append({
            "type": "show_understanding",
            "requires_confirmation": True,
            "reason": "active_rule: show_understanding_before_execution",
        })

    steps.append({"type": "execute_task_stub", "requires_confirmation": False})

    if active_program.verification_policy.get("must_check_success_condition"):
        steps.append({"type": "verify_success_condition", "requires_confirmation": False})

    return steps
```

## 17. Query response format

```json
{
  "assistant_response": "Активная версия программы: 3.

Автоматически применяемые правила:
1. Перед задачей показывать понимание. Scope: all_tasks.

Сохранённые future rules:
1. Для code_review задач добавлять список найденных багов. Не применяется автоматически в v1.1.1.

Ожидающие кандидаты: нет.

Политика памяти: выключена.",
  "data": {
    "active_version": 3,
    "enforced_rules": [
      {
        "key": "show_understanding_before_execution",
        "text": "Перед задачей показывать понимание.",
        "scope": "all_tasks",
        "application_mode": "enforced_by_rule_engine",
        "status": "active"
      }
    ],
    "future_rules": [
      {
        "key": null,
        "text": "Для code_review задач добавлять список найденных багов.",
        "scope": "code_review",
        "application_mode": "future_rule",
        "status": "future"
      }
    ],
    "pending_candidates": [],
    "policies": {
      "memory_policy": {"enabled": false, "retention": "episode"},
      "verification_policy": {
        "must_check_success_condition": true,
        "default_success_condition_mode": "completed_status_is_success"
      }
    }
  }
}
```

## 18. EvidenceEvent event types

```text
llm_schema_validation_failed
mandatory_fields_missing
ambiguous_request_logged
rule_candidate_created
future_rule_saved
rule_activated
pending_switch_requested
pending_cancelled_by_user_switch
episode_cancelled_by_user
task_completed
verification_completed
feedback_received
```

## 19. Acceptance tests

Required tests:

```text
test_no_mixed_intent
test_chat_vs_vague_task
test_ambiguous_request_not_executed
test_item_level_validation_task_plus_rule
test_unknown_key_rule_becomes_future_rule
test_future_rule_not_enforced_by_rule_engine
test_pending_switch_requires_confirmation
test_pending_switch_yes_cancels_old_and_starts_new
test_pending_switch_no_returns_to_pending
test_exact_short_command_only
test_no_substring_false_positive
test_fallback_escalation
test_unknown_utterance_logged
test_requires_user_review_logic
test_query_returns_enforced_and_future_rules
test_cancel_flow
test_rule_engine_applies_show_understanding
test_llm_invalid_schema_fallback
```

## 20. Definition of Done

MVP is accepted only if:

```text
no mixed primary_intent
all semantic parsing is LLMClassifier or test StubClassifier
exact command matching only
vague task does not execute
ambiguous_request is clarified and logged
unsupported rules are not marked enforced
future rules are queryable
pending switch requires explicit confirmation
fallback escalation works
unknown_utterances are recorded
RuleEngine affects runtime for known keys
Program versions are immutable
evidence is recorded
side effects are not executed
```
