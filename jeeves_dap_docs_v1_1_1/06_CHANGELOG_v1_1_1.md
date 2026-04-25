# Changelog — Jeeves DAP v1.1.1

## 1. Added ambiguous_request

Vague requests are no longer treated as malformed task by default.

Example:

```text
Сделай что-нибудь хорошее
```

becomes:

```json
{
  "primary_intent": "chat",
  "items": [{"type": "ambiguous_request"}],
  "needs_clarification": true
}
```

## 2. Added chat vs vague task rule

A valid task requires:

```text
action
object / target
expected result or implied deliverable
```

## 3. Added item-level validation

Sufficiency is no longer checked only against `primary_intent`.

Every actionable item is validated independently.

## 4. Kept no-mixed decision

`mixed` remains banned.

The correct model remains:

```text
one primary_intent
multiple items
```

## 5. Added future_rule for unsupported rules

Rules without known key are not enforced.

They are stored as:

```text
status = future
application_mode = future_rule
```

## 6. Added pending switch confirmation

New unrelated task during pending review no longer cancels old state silently.

## 7. Added DeferredMessage

Used to hold the new message while waiting for pending switch confirmation.

## 8. Added exact command matching

PreProcessor uses exact short commands only.

No substring matching.

## 9. Added optional quick replies

UI may show:

```text
[Да] [Нет] [Отмена]
```

They only submit exact text messages.

## 10. Added fallback escalation

Fallback message changes after repeated failures.

## 11. Query response now separates rule types

Query output must separate:

```text
enforced rules
future rules
pending candidates
policies
```

## 12. Acceptance tests expanded

Added tests for:

```text
chat vs vague task
ambiguous_request
future_rule
pending switch
exact command matching
fallback escalation
query enforced vs future rules
```
