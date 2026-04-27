# Jeeves DAP

Jeeves DAP MVP is a chat-first agent backend. User messages are parsed into
structured intake results, rules can be proposed and confirmed through chat, and
tasks can be executed through explicit runtime modes.

This repository is currently a backend prototype. It is designed to make the
agent's understanding, confirmation state, rules, and runtime result explicit
before any task execution is reported.

## Current Status

Tests pass, but this is still an MVP/backend prototype. The current system has
a working FastAPI app, in-memory repositories, deterministic chat confirmation
flows, stub task execution, and a read-only repository review runtime.

The next product milestone is a documented runnable local API flow with a real
LLM intake client behind an explicit feature flag.

## Current MVP Flow

1. Create an episode.
2. Send a user message to the episode.
3. The classifier produces an `IntakeResult`.
4. The orchestrator handles the deterministic preprocessor before semantic
   classification. Text commands such as `да`, `нет`, and `отмена` are handled
   before classifier output is used.
5. Rule updates create rule candidates and require user confirmation.
6. When the active program has `show_understanding_before_execution`, task
   messages create a pending understanding instead of executing immediately.
7. The user confirms the pending understanding with text `да` or rejects it
   with text `нет`.
8. Runtime execution happens only after the required confirmation has been
   satisfied.

## What Currently Works

- FastAPI app object exists at `jeeves_dap.api:app`.
- `GET /api/health`
- `POST /api/episodes`
- `POST /api/turns`
- `GET /api/program/current`
- `DevCommandClassifier` slash commands for local/manual flows:
  - `/task ...`
  - `/rule ...`
  - `/future-rule ...`
  - `/query`
  - `/ambiguous ...`
- `LLMIntakeClassifier` seam with an injected client only.
- Model routing config without real network calls.
- Stub task runtime for normal tasks.
- Read-only repository review runtime for explicit repository review tasks.
- Fallback and unknown utterance handling.
- Pending switch handling when a new message arrives during a pending review.
- Rule candidate confirmation and rejection.

## What Is Stubbed Or Not Real Yet

- There are no real LLM API calls yet.
- There is no real task execution except read-only repository review.
- Normal task execution is still `stub` mode.
- No persistent production database setup is documented.
- No authentication is implemented.
- No production deployment is documented.
- No background worker is implemented.

## Run Tests

The verified project check command is:

```bash
./scripts/check.sh
```

This runs the pytest suite, checks that the domain layer does not import
forbidden layers, and checks Python files for known mojibake markers.

## Run The API Locally

After dependencies are installed, start the FastAPI app with:

```bash
PYTHONPATH=src python3 -m uvicorn jeeves_dap.api:app --host 127.0.0.1 --port 8001
```

The FastAPI app entrypoint is `jeeves_dap.api:app`. Open the browser at:

```text
http://127.0.0.1:8001
```

## Manual Smoke Test

Start the API locally first, then run these commands from another shell:

```bash
curl -s http://127.0.0.1:8001/api/health
```

Create an episode:

```bash
EPISODE_ID="$(
  curl -s -X POST http://127.0.0.1:8001/api/episodes \
    | python -c 'import json,sys; print(json.load(sys.stdin)["episode_id"])'
)"
echo "$EPISODE_ID"
```

Query the current program:

```bash
curl -s -X POST http://127.0.0.1:8001/api/turns \
  -H 'Content-Type: application/json' \
  -d "{\"episode_id\":\"$EPISODE_ID\",\"text\":\"/query\"}"
```

Propose the rule that shows understanding before execution:

```bash
curl -s -X POST http://127.0.0.1:8001/api/turns \
  -H 'Content-Type: application/json' \
  -d "{\"episode_id\":\"$EPISODE_ID\",\"text\":\"/rule Показывай понимание\"}"
```

Confirm the rule with text `да`:

```bash
curl -s -X POST http://127.0.0.1:8001/api/turns \
  -H 'Content-Type: application/json' \
  -d "{\"episode_id\":\"$EPISODE_ID\",\"text\":\"да\"}"
```

Send a normal task:

```bash
curl -s -X POST http://127.0.0.1:8001/api/turns \
  -H 'Content-Type: application/json' \
  -d "{\"episode_id\":\"$EPISODE_ID\",\"text\":\"/task Проверить код\"}"
```

Expected result: because `show_understanding_before_execution` is active, the
response should have `episode_state` set to `pending_understanding_review`.

Confirm with text `да`:

```bash
curl -s -X POST http://127.0.0.1:8001/api/turns \
  -H 'Content-Type: application/json' \
  -d "{\"episode_id\":\"$EPISODE_ID\",\"text\":\"да\"}"
```

Expected result: the response should include `runtime_result.execution_mode`
set to `stub` and `runtime_result.did_execute_real_work` set to `false`.

## Runtime Modes

### `stub`

Normal task execution returns a stub result. `did_execute_real_work` is `false`.
This means the backend built a runtime plan and verification result, but did
not perform real work for the task.

### `read_only_repo_review`

Explicit repository review tasks use the read-only repository review runtime.
`did_execute_real_work` is `true` because the runtime actually inspects the
repository with read-only commands and returns a report. It must not mutate
repository files.

## Safety Rules

- No UI buttons are required for core confirmation flows.
- Confirmations are text-only: use `да`, `нет`, or `отмена`.
- Ambiguous or vague tasks ask for clarification instead of executing.
- Read-only repository review must not mutate repository files.
- `.env` must not be committed.
