# Jeeves DAP — Dialogue-Formed Agent Program

Version: 1.1.1
Status: developer handoff package

## 1. Название

**Jeeves DAP** — **Dialogue-Formed Agent Program**.

Русское рабочее название: **диалогово формируемая программа агента**.

## 2. Что мы хотим сделать

Jeeves DAP — это персональный агент, чья рабочая программа формируется не заранее в жёстком prompt’е, а через диалог с пользователем.

Система должна:

1. принимать естественные сообщения пользователя;
2. распознавать короткие управляющие команды `да` / `нет` / `отмена` до LLM;
3. всю семантику обрабатывать через LLM со schema validation;
4. проверять заполненность обязательных полей контракта;
5. валидировать не только `primary_intent`, но и каждый actionable item;
6. различать задачу, правило, correction, feedback, query, cancel, chat и ambiguous request;
7. не исполнять размытые задачи;
8. не обещать автоматическое применение правил, которые Rule Engine не поддерживает;
9. не отменять pending-эпизоды молча;
10. вести версионированную Agent Program;
11. фиксировать evidence и unknown utterances.

## 3. Главный runtime-flow

```text
User message
↓
DeterministicPreProcessor
  only exact yes/no/cancel
↓
LLMClassifier
  intent + items + understanding
↓
Schema validation
↓
Mandatory field check
↓
Item-level validation
↓
Flow decision
↓
ProgramService / RuleEngine / TaskRuntimeStub
↓
VerifierStub
↓
EvidenceEvent + UnknownUtterance where needed
```

## 4. Главное решение по intent

`mixed` не используется как `primary_intent`.

Правильная модель:

```json
{
  "primary_intent": "task",
  "items": [
    {"type": "task", "text": "Проверить код"},
    {"type": "rule_candidate", "text": "Для таких задач сначала писать ожидаемый результат"}
  ]
}
```

Смысл:

```text
primary_intent = какой flow ведёт сообщение
items = какие объекты извлечены из сообщения
```

## 5. Новое в v1.1.1

```text
1. ambiguous_request для размытых сообщений;
2. явное правило chat vs vague task;
3. item-level validation;
4. future_rule для правил без known key;
5. pending_switch_confirmation вместо молчаливой отмены;
6. optional quick replies как UI-обёртка над текстом;
7. fallback escalation.
```

## 6. Chat vs vague task

Система не должна превращать любую абстрактную фразу в task.

Пример:

```text
Сделай что-нибудь хорошее.
```

Это не валидная задача, потому что нет конкретного действия, объекта и ожидаемого результата.

Правильная интерпретация:

```json
{
  "primary_intent": "chat",
  "items": [
    {"type": "ambiguous_request", "text": "Сделай что-нибудь хорошее"}
  ],
  "needs_clarification": true
}
```

Ответ:

```text
Я не вижу конкретной задачи. Что именно нужно сделать: написать текст, проверить код, составить документ или просто обсудить идею?
```

## 7. Unsupported rules

MVP Rule Engine исполняет только known keys:

```text
show_understanding_before_execution
```

Если правило не имеет known key, оно не может быть `active enforced rule`.

Правильный статус:

```text
future_rule
unsupported_in_current_version
```

Ответ пользователю:

```text
Я понял это как правило, но в текущей версии не умею применять его автоматически. Могу сохранить его как future rule, чтобы использовать позже. Сохранить?
```

## 8. Pending switch confirmation

Если есть неподтверждённое понимание или rule candidate, а пользователь присылает новое сообщение по другой теме, система не закрывает старый эпизод молча.

Flow:

```text
pending_understanding_review / pending_rule_review
↓
new unrelated semantic message
↓
pending_switch_confirmation
↓
“У нас осталось неподтверждённое правило/понимание. Если перейти к новому сообщению или новой теме, оно будет отменено. Отменить его и продолжить с новым сообщением?”
```

## 9. Text-only protocol and quick replies

Core protocol is text-only.

UI may show:

```text
[Да] [Нет] [Отмена]
```

These quick replies only submit exact text messages into the same chat protocol.

## 10. MVP success criterion

MVP is successful only if:

```text
enforceable rule can be created and confirmed
Agent Program version increments
RuleEngine changes task flow
vague task is clarified, not executed
unsupported rule is stored only as future_rule
pending switch requires explicit confirmation
query shows enforced and future rules separately
fallback escalation and unknown_utterances work
```
