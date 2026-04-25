# Developer Handoff — Jeeves DAP MVP

Version: 1.1.1

## 1. Build target

Implement the MVP vertical slice exactly as specified:

```text
text message
↓
exact yes/no/cancel pre-processing
↓
LLMClassifier / StubClassifier
↓
schema validation
↓
mandatory field check
↓
item-level validation
↓
flow routing
↓
Agent Program update or task execution
↓
EvidenceEvent
↓
UnknownUtterance where needed
```

## 2. Non-negotiable rules

### 2.1 No mixed

Never return:

```json
{"primary_intent": "mixed"}
```

### 2.2 No production semantic keyword router

Deterministic logic may handle only exact short commands.

### 2.3 Exact command matching only

This must not trigger deterministic reject:

```text
Так, подожди, нет, дай подумать.
```

### 2.4 Vague task must not execute

If request lacks concrete action / target / result, classify as:

```json
{
  "primary_intent": "chat",
  "items": [{"type": "ambiguous_request"}],
  "needs_clarification": true
}
```

### 2.5 Unsupported rules must not be called active enforced rules

If rule has no known key:

```text
application_mode = future_rule
status = future after confirmation
```

### 2.6 Pending state must not be silently cancelled

If a new unrelated message or topic arrives during pending review, ask pending switch confirmation.

### 2.7 Core protocol is text-only

Optional UI quick replies are allowed only if they submit exact text messages.

### 2.8 Side effects disabled

No sending email, editing files, publishing, deleting, calendar mutation or remote writes in MVP.

## 3. Required services

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

## 4. DeterministicPreProcessor pseudocode

```python
CONFIRM = {"да", "верно", "подтверждаю", "так", "сохрани", "конечно"}
REJECT = {"нет", "не так", "не подтверждаю", "не сохраняй", "не нужно"}
CANCEL = {"отмена", "забудь", "начнём заново", "начать заново", "отменить"}

def normalize_command(text: str) -> str:
    return strip_boundary_punctuation(collapse_spaces(text.lower().strip()))

def preprocess(text: str, episode_state: str) -> PreprocessResult | None:
    cmd = normalize_command(text)

    if cmd in CANCEL:
        return PreprocessResult(type="cancel")

    if episode_state in {
        "pending_understanding_review",
        "pending_rule_review",
        "pending_switch_confirmation",
    }:
        if cmd in CONFIRM:
            return PreprocessResult(type="confirm")
        if cmd in REJECT:
            return PreprocessResult(type="reject")

    return None
```

## 5. Item validation pseudocode

```python
KNOWN_RULE_KEYS = {
    "show_understanding_before_execution",
}

def validate_item(item):
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

## 6. Pending switch pseudocode

```python
def handle_semantic_message_in_pending_state(episode, message, intake):
    if episode.state not in {"pending_understanding_review", "pending_rule_review"}:
        return continue_normal_flow()

    if intake.primary_intent in {"correction", "feedback", "cancel"}:
        return continue_normal_flow()

    if is_related_to_pending(episode, intake):
        return continue_normal_flow()

    save_deferred_message(episode.id, message, intake)
    episode.cached_state = "pending_switch_confirmation"

    evidence_service.record(
        event_type="pending_switch_requested",
        episode_id=episode.id,
        message_id=message.id,
        result="waiting_for_user",
    )

    return {
        "assistant_response": "У нас осталось неподтверждённое правило/понимание. Если перейти к новому сообщению или новой теме, оно будет отменено. Отменить его и продолжить с новым сообщением?",
        "state": "pending_switch_confirmation",
    }
```

## 7. Future rule response

When rule is unsupported:

```python
response = (
    "Я понял это как правило, но в текущей версии не умею применять его автоматически. "
    "Могу сохранить его как future rule, чтобы использовать позже. Сохранить?"
)
```

If confirmed:

```text
RuleCandidate.status = future
application_mode = future_rule
AgentProgramVersion vN+1 created
```

For `task + unsupported rule` in one message:

```text
task remains the primary flow
assistant does not create a hidden yes/no state for this choice
assistant says the task will execute under the current program
unsupported rule may be saved later as a separate future_rule message
```

## 8. Fallback escalation pseudocode

```python
def fallback_response(episode, reason):
    episode.fallback_count += 1

    unknown_utterance_service.record(
        episode_id=episode.id,
        reason=reason,
        fallback_count=episode.fallback_count,
        context_snapshot=get_context_snapshot(episode.id),
    )

    if episode.fallback_count == 1:
        return "Я не смог понять запрос. Уточните, что нужно сделать."

    if episode.fallback_count == 2:
        return "Мне всё ещё неясно. Напишите в формате: “сделай X”, “запомни правило Y” или “отмени”."

    return "Похоже, сейчас лучше сначала обсудить цель. Что вы хотите получить в результате?"
```

Reset `fallback_count` after successful semantic understanding.

## 9. First PR

First PR should include only:

```text
models
repositories
Agent Program v1 defaults
DeterministicPreProcessor
IntentClassifier interface
StubClassifier for tests
item validation
unknown_utterances
EvidenceService
unit tests for exact command matching and no mixed
```

Do not implement UI first.
Do not implement memory first.
Do not implement side effects.
