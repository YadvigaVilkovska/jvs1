# Product Description — Jeeves DAP

Version: 1.1.1

## 1. Product summary

Jeeves DAP is a dialogue-formed personal agent runtime.

It builds a structured, versioned Agent Program through dialogue instead of relying on a single static prompt.

## 2. Core UX

The agent:

1. handles short `да` / `нет` / `отмена` commands deterministically only when state expects control input;
2. uses LLM structured output for semantic parsing;
3. asks clarification for vague requests;
4. separates enforced rules from future rules;
5. never silently discards pending review;
6. keeps all control possible through normal text.

## 3. Scenario: enforceable rule

User:

```text
В будущем перед выполнением задачи сначала показывай, как ты её понял.
```

System:

```text
Я понял это как правило: перед выполнением задачи сначала показывать нормализованное понимание.

Это правило поддерживается текущим Rule Engine и может применяться автоматически. Сохранить и активировать?
```

User:

```text
Да.
```

System creates Agent Program v2.

## 4. Scenario: unsupported rule

User:

```text
Если я прошу проверить код, всегда добавляй список найденных багов.
```

System:

```text
Я понял это как правило для задач проверки кода.

Но в текущей версии я не умею применять это правило автоматически: для него нет поддерживаемого системного ключа.

Я могу сохранить его как future rule, чтобы использовать в следующих версиях. Сохранить как future rule?
```

The rule must not be shown as `enforced_by_rule_engine`.

## 5. Scenario: task + rule in one message

User:

```text
Проверь код. И для таких задач всегда сначала пиши ожидаемый результат.
```

Internal:

```json
{
  "primary_intent": "task",
  "items": [
    {"type": "task", "text": "Проверить код"},
    {"type": "rule_candidate", "text": "Для задач проверки кода сначала писать ожидаемый результат"}
  ]
}
```

System validates both items separately.

If task is valid but rule is unsupported, system keeps the task as the primary flow and says:

```text
Я вижу две части:
1. задача: проверить код;
2. новое правило: сначала писать ожидаемый результат.

Задачу выполню в текущем режиме.

Это правило не поддерживается автоматически в текущей версии. Если позже захотите, я смогу сохранить его отдельным сообщением как future rule.
```

## 6. Scenario: query active program

User:

```text
Какие правила сейчас активны?
```

System:

```text
Активная версия программы: 3.

Автоматически применяемые правила:
1. Перед задачей показывать понимание. Scope: all_tasks.

Сохранённые future rules:
1. Для code_review задач добавлять список найденных багов. Не применяется автоматически в v1.1.1.

Ожидающие кандидаты: нет.
Политика памяти: выключена.
```

## 7. Scenario: vague request

User:

```text
Сделай что-нибудь хорошее.
```

System:

```text
Я не вижу конкретной задачи. Что именно нужно сделать: написать текст, проверить код, составить документ или просто обсудить идею?
```

No task execution.

## 8. Scenario: new topic during pending review

System has pending rule candidate.

User:

```text
А какая завтра погода?
```

System:

```text
У нас осталось неподтверждённое правило.

Если перейти к новому сообщению или новой теме, это неподтверждённое правило будет отменено. Отменить его и продолжить с новым сообщением?
```

Allowed replies:

```text
Да
Нет
Отмена
```

## 9. Product constraints

1. No `mixed` primary intent.
2. No production keyword semantic router.
3. No fake enforced rules.
4. No silent pending cancellation.
5. No execution of vague task.
6. No side effects in MVP.
7. No identical fallback repeated endlessly.

## 10. Fallback escalation

```text
fallback_count = 1:
Я не смог понять запрос. Уточните, что нужно сделать.

fallback_count = 2:
Мне всё ещё неясно. Напишите в формате: “сделай X”, “запомни правило Y” или “отмени”.

fallback_count >= 3:
Похоже, сейчас лучше сначала обсудить цель. Что вы хотите получить в результате?
```
