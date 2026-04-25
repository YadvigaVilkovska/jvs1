# Patch Summary — v1.1.1

## Accepted from critique

```text
chat vs vague task risk
unsupported rule trust risk
pending episode silent cancellation risk
fallback repetition risk
quick reply UX improvement
```

## Rejected from critique

```text
returning mixed as primary_intent
```

Reason:

```text
mixed does not define control flow.
primary_intent + items is still the correct architecture.
```

## Final architecture rule

```text
primary_intent decides flow
items decide extracted objects
item-level validation decides what can be processed
RuleEngine decides what is actually enforceable
```

## Rule honesty requirement

The system must never imply that a rule is automatically enforced unless:

```text
rule.key is known
application_mode = enforced_by_rule_engine
RuleEngine actually uses it
```

## Pending safety requirement

The system must never silently discard a pending rule or understanding when a new message arrives.

Use:

```text
pending_switch_confirmation
```

## UX rule

Core backend remains text-only.

Optional quick replies are allowed only as exact text submitters.
