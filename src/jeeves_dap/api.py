"""Contract: minimal FastAPI entrypoint for manual Jeeves DAP API testing without UI or LLM."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from jeeves_dap.domain.models import Episode, IntakeResult, UserMessage
from jeeves_dap.repositories.agent_program_repository import (
    AgentProgramVersionRepository,
    InMemoryAgentProgramVersionRepository,
)
from jeeves_dap.repositories.deferred_message_repository import (
    DeferredMessageRepository,
    InMemoryDeferredMessageRepository,
)
from jeeves_dap.repositories.episode_repository import EpisodeRepository, InMemoryEpisodeRepository
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
)
from jeeves_dap.repositories.user_message_repository import (
    InMemoryUserMessageRepository,
    UserMessageRepository,
)
from jeeves_dap.services.agent_program_service import AgentProgramService
from jeeves_dap.services.classification import DevCommandClassifier, IntentClassifier
from jeeves_dap.services.deterministic_preprocessor import DeterministicPreProcessor
from jeeves_dap.services.orchestrator import Orchestrator
from jeeves_dap.services.pending_switch_service import PendingSwitchService
from jeeves_dap.services.rule_engine import RuleEngine
from jeeves_dap.services.task_runtime_stub import TaskRuntimeStub
from jeeves_dap.services.verifier_stub import VerifierStub


class HealthResponse(BaseModel):
    """Contract: health response payload for the API."""

    status: str


class CreateEpisodeResponse(BaseModel):
    """Contract: episode creation response payload."""

    episode_id: str
    episode_state: str
    fallback_count: int
    program_version: int


class CreateTurnRequest(BaseModel):
    """Contract: request payload for one orchestrated turn."""

    episode_id: str
    text: str


class TurnResponse(BaseModel):
    """Contract: response payload for one orchestrated turn."""

    episode_id: str
    episode_state: str
    fallback_count: int
    assistant_response: str
    intake_result: dict[str, Any] | None = None
    runtime_result: dict[str, Any] | None = None
    rule_candidate: dict[str, Any] | None = None
    pending_switch_decision: dict[str, Any] | None = None
    unknown_utterance: dict[str, Any] | None = None
    program_version: int | None = None


class ProgramCurrentResponse(BaseModel):
    """Contract: current program inspection response payload."""

    active_version: int
    enforced_rules: list[dict[str, Any]]
    future_rules: list[dict[str, Any]]
    pending_candidates: list[dict[str, Any]]
    policies: dict[str, Any]


ROOT_HTML = """<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <title>Jeeves DAP</title>
    <style>
      :root {
        color-scheme: light;
        --bg: #f4efe7;
        --card: #fffaf4;
        --accent: #1f6f78;
        --accent-soft: #d7ecee;
        --user: #d6f4de;
        --assistant: #ffffff;
        --text: #1f2933;
        --muted: #52606d;
        --border: #d9e2ec;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background:
          radial-gradient(circle at top, #fff8ef 0%, rgba(255, 248, 239, 0) 40%),
          linear-gradient(180deg, #f8f2ea 0%, var(--bg) 100%);
        color: var(--text);
      }
      .app {
        max-width: 480px;
        margin: 0 auto;
        min-height: 100dvh;
        display: grid;
        grid-template-rows: auto 1fr auto;
        background: rgba(255,255,255,0.45);
        backdrop-filter: blur(10px);
      }
      .header {
        padding: 16px 18px 12px;
        border-bottom: 1px solid var(--border);
        background: rgba(255,255,255,0.7);
        position: sticky;
        top: 0;
        z-index: 1;
      }
      .title {
        font-size: 18px;
        font-weight: 700;
      }
      .subtitle {
        margin-top: 4px;
        font-size: 12px;
        color: var(--muted);
      }
      .status {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        margin-top: 12px;
        font-size: 12px;
        color: var(--muted);
      }
      .history {
        padding: 18px 14px 96px;
        overflow-y: auto;
      }
      .bubble {
        max-width: 85%;
        margin-bottom: 12px;
        padding: 10px 12px;
        border-radius: 18px;
        border: 1px solid var(--border);
        box-shadow: 0 6px 16px rgba(15, 23, 42, 0.05);
        white-space: pre-wrap;
        word-break: break-word;
      }
      .bubble.user {
        margin-left: auto;
        background: var(--user);
      }
      .bubble.assistant {
        margin-right: auto;
        background: var(--assistant);
      }
      .composer {
        position: sticky;
        bottom: 0;
        background: rgba(255,255,255,0.9);
        border-top: 1px solid var(--border);
        padding: 12px;
      }
      form {
        display: grid;
        gap: 8px;
      }
      input[type="text"] {
        width: 100%;
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 14px 16px;
        font-size: 16px;
        outline: none;
        background: white;
      }
      .hint {
        font-size: 12px;
        color: var(--muted);
        line-height: 1.4;
      }
      details {
        margin-top: 12px;
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 10px 12px;
      }
      pre {
        margin: 10px 0 0;
        font-size: 12px;
        overflow-x: auto;
        white-space: pre-wrap;
      }
    </style>
  </head>
  <body>
    <main class="app">
      <header class="header">
        <div class="title">Jeeves DAP</div>
        <div class="subtitle">Тонкий UI для ручной проверки API-потока.</div>
        <div class="status">
          <span>episode_state: <strong id="episode-state">loading</strong></span>
          <span>fallback_count: <strong id="fallback-count">0</strong></span>
          <span>program_version: <strong id="program-version">-</strong></span>
        </div>
      </header>
      <section id="chat-history" class="history" aria-live="polite"></section>
      <section class="composer">
        <form id="turn-form">
          <input id="turn-input" type="text" placeholder="Напишите сообщение и нажмите Enter" autocomplete="off" />
        </form>
        <div class="hint">
          Подтверждение и отклонение только текстом: напишите "да", "нет" или "отмена".
        </div>
        <div class="hint">
          Dev commands: /task ..., /rule ..., /future-rule ..., /query, /ambiguous ...
        </div>
        <details>
          <summary>Последний raw JSON response</summary>
          <pre id="debug-json">{}</pre>
        </details>
      </section>
    </main>
    <script>
      const chatHistory = document.getElementById("chat-history");
      const turnForm = document.getElementById("turn-form");
      const turnInput = document.getElementById("turn-input");
      const episodeState = document.getElementById("episode-state");
      const fallbackCount = document.getElementById("fallback-count");
      const programVersion = document.getElementById("program-version");
      const debugJson = document.getElementById("debug-json");

      let currentEpisodeId = null;

      function appendBubble(role, text) {
        const bubble = document.createElement("div");
        bubble.className = `bubble ${role}`;
        bubble.textContent = text;
        chatHistory.appendChild(bubble);
        chatHistory.scrollTop = chatHistory.scrollHeight;
      }

      function updateMeta(payload) {
        episodeState.textContent = payload.episode_state ?? episodeState.textContent;
        fallbackCount.textContent = payload.fallback_count ?? fallbackCount.textContent;
        programVersion.textContent = payload.program_version ?? programVersion.textContent;
        debugJson.textContent = JSON.stringify(payload, null, 2);
      }

      async function createEpisode() {
        const response = await fetch("/api/episodes", { method: "POST" });
        const payload = await response.json();
        currentEpisodeId = payload.episode_id;
        updateMeta(payload);
        appendBubble("assistant", "Эпизод создан. Можно писать сообщения.");
      }

      async function submitTurn(text) {
        appendBubble("user", text);
        const response = await fetch("/api/turns", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ episode_id: currentEpisodeId, text }),
        });
        const payload = await response.json();
        updateMeta(payload);
        appendBubble("assistant", payload.assistant_response);
      }

      turnForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const text = turnInput.value.trim();
        if (!text || !currentEpisodeId) {
          return;
        }
        turnInput.value = "";
        await submitTurn(text);
      });

      createEpisode();
    </script>
  </body>
</html>
"""


def serialize_value(value: Any) -> Any:
    """Convert dataclasses, tuples, and datetimes into JSON-serializable values."""

    if is_dataclass(value):
        return {key: serialize_value(item) for key, item in asdict(value).items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (tuple, list)):
        return [serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): serialize_value(item) for key, item in value.items()}
    return value


def get_current_program_version(repository: AgentProgramVersionRepository):
    """Return the latest stored program version when it exists."""

    versions = repository.list_versions()
    return versions[-1] if versions else None


def create_app(
    *,
    classifier: IntentClassifier | None = None,
    episode_repository: EpisodeRepository | None = None,
    user_message_repository: UserMessageRepository | None = None,
    program_version_repository: AgentProgramVersionRepository | None = None,
    rule_candidate_repository: RuleCandidateRepository | None = None,
    pending_understanding_repository: PendingUnderstandingRepository | None = None,
    unknown_utterance_repository: UnknownUtteranceRepository | None = None,
    deferred_message_repository: DeferredMessageRepository | None = None,
) -> FastAPI:
    """Create the API app with in-memory defaults and overridable dependencies for tests."""

    classifier_dependency = classifier or DevCommandClassifier()
    uses_default_classifier = classifier is None
    episode_repository_dependency = episode_repository or InMemoryEpisodeRepository()
    user_message_repository_dependency = user_message_repository or InMemoryUserMessageRepository()
    program_version_repository_dependency = (
        program_version_repository or InMemoryAgentProgramVersionRepository()
    )
    rule_candidate_repository_dependency = (
        rule_candidate_repository or InMemoryRuleCandidateRepository()
    )
    pending_understanding_repository_dependency = (
        pending_understanding_repository or InMemoryPendingUnderstandingRepository()
    )
    unknown_utterance_repository_dependency = (
        unknown_utterance_repository or InMemoryUnknownUtteranceRepository()
    )
    deferred_message_repository_dependency = (
        deferred_message_repository or InMemoryDeferredMessageRepository()
    )

    program_service = AgentProgramService(program_version_repository_dependency)
    pending_switch_service = PendingSwitchService(deferred_message_repository_dependency)
    orchestrator = Orchestrator(
        classifier=classifier_dependency,
        preprocessor=DeterministicPreProcessor(),
        program_service=program_service,
        rule_candidate_repository=rule_candidate_repository_dependency,
        pending_understanding_repository=pending_understanding_repository_dependency,
        unknown_utterance_repository=unknown_utterance_repository_dependency,
        pending_switch_service=pending_switch_service,
        task_runtime=TaskRuntimeStub(RuleEngine(), VerifierStub()),
    )

    app = FastAPI(title="Jeeves DAP API")

    @app.get("/", response_class=HTMLResponse)
    def root_ui() -> HTMLResponse:
        """Return a minimal inline HTML UI for manual API testing."""

        return HTMLResponse(ROOT_HTML)

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        """Return a minimal health signal for manual integration checks."""

        return HealthResponse(status="ok")

    @app.post("/api/episodes", response_model=CreateEpisodeResponse)
    def create_episode() -> CreateEpisodeResponse:
        """Create one episode and ensure the initial program version exists."""

        created_at = datetime.now(UTC)
        active_version = program_service.create_initial_version("v1", created_at)
        episode = Episode(
            id=str(uuid4()),
            user_id="anonymous",
            state="open",
            created_at=created_at,
            updated_at=created_at,
        )
        episode_repository_dependency.save(episode)
        return CreateEpisodeResponse(
            episode_id=episode.id,
            episode_state=episode.state,
            fallback_count=episode.fallback_count,
            program_version=active_version.version_number,
        )

    @app.post("/api/turns", response_model=TurnResponse)
    def create_turn(payload: CreateTurnRequest) -> TurnResponse:
        """Create one turn, delegate to the orchestrator, and persist the updated episode."""

        episode = episode_repository_dependency.get_by_id(payload.episode_id)
        if episode is None:
            raise HTTPException(status_code=404, detail="Episode not found.")

        created_at = datetime.now(UTC)
        active_version = program_service.create_initial_version("v1", created_at)
        current_program_version = get_current_program_version(program_version_repository_dependency) or active_version
        user_message = UserMessage(
            id=str(uuid4()),
            episode_id=episode.id,
            text=payload.text,
            created_at=created_at,
        )
        user_message_repository_dependency.save(user_message)

        turn_result = orchestrator.handle_message(episode, user_message, current_program_version)
        if uses_default_classifier and turn_result.intake_result is not None:
            turn_result = replace(
                turn_result,
                intake_result=replace(turn_result.intake_result, message_id=user_message.id),
            )
        episode_repository_dependency.save(turn_result.episode)

        return TurnResponse(
            episode_id=turn_result.episode.id,
            episode_state=turn_result.episode.state,
            fallback_count=turn_result.episode.fallback_count,
            assistant_response=turn_result.assistant_response,
            intake_result=serialize_value(turn_result.intake_result),
            runtime_result=serialize_value(turn_result.runtime_result),
            rule_candidate=serialize_value(turn_result.rule_candidate),
            pending_switch_decision=serialize_value(turn_result.pending_switch_decision),
            unknown_utterance=serialize_value(turn_result.unknown_utterance),
            program_version=(
                turn_result.program_version.version_number if turn_result.program_version is not None else None
            ),
        )

    @app.get("/api/program/current", response_model=ProgramCurrentResponse)
    def get_current_program() -> ProgramCurrentResponse:
        """Return the current query program contract for manual inspection."""

        created_at = datetime.now(UTC)
        active_version = program_service.create_initial_version("v1", created_at)
        current_program_version = get_current_program_version(program_version_repository_dependency) or active_version
        contract = program_service.build_query_program_contract(
            active_version=current_program_version,
            pending_candidates=(),
        )
        serialized_contract = serialize_value(contract)
        return ProgramCurrentResponse(**serialized_contract)

    return app


app = create_app()
