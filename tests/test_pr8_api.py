"""Contract: PR-8 regression tests for the minimal FastAPI API vertical slice."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from jeeves_dap.api import create_app, serialize_value
from jeeves_dap.domain.models import IntakeResult, MessageItem
from jeeves_dap.repositories.episode_repository import InMemoryEpisodeRepository
from jeeves_dap.repositories.pending_understanding_repository import InMemoryPendingUnderstandingRepository
from jeeves_dap.repositories.rule_candidate_repository import InMemoryRuleCandidateRepository
from jeeves_dap.services.classification import StubClassifier


def create_episode_and_return_id(client: TestClient) -> str:
    """Create one episode through the API and return its id."""

    response = client.post("/api/episodes")
    assert response.status_code == 200
    return response.json()["episode_id"]


def test_health_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {"status": "ok"}
    assert set(payload) == {"status"}


def test_root_ui_returns_html() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<!doctype html>" in response.text.lower()


def test_root_ui_contains_chat_mount() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert 'id="chat-history"' in response.text


def test_root_ui_references_api_episodes() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert "/api/episodes" in response.text


def test_root_ui_references_api_turns() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert "/api/turns" in response.text


def test_root_ui_has_no_confirm_reject_buttons() -> None:
    client = TestClient(create_app())

    response = client.get("/")
    html = response.text.lower()

    assert "confirm" not in html
    assert "reject" not in html
    assert ">да<" not in html
    assert ">нет<" not in html
    assert "<button" not in html


def test_api_no_buttons_added() -> None:
    client = TestClient(create_app())

    response = client.get("/")
    html = response.text.lower()

    assert "<button" not in html
    assert "onclick=" not in html


def test_root_ui_mentions_text_only_confirmation() -> None:
    client = TestClient(create_app())

    response = client.get("/")
    html = response.text

    assert '"да"' in html
    assert '"нет"' in html
    assert '"отмена"' in html


def test_ui_mentions_dev_commands() -> None:
    client = TestClient(create_app())

    response = client.get("/")
    html = response.text

    assert "Dev commands:" in html
    assert "/task ..." in html
    assert "/rule ..." in html
    assert "/future-rule ..." in html
    assert "/query" in html
    assert "/ambiguous ..." in html


def test_create_episode_endpoint() -> None:
    client = TestClient(create_app())

    response = client.post("/api/episodes")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"episode_id", "episode_state", "fallback_count", "program_version"}
    assert payload["episode_state"] == "open"
    assert payload["fallback_count"] == 0
    assert payload["program_version"] == 1
    assert payload["episode_id"]


def test_turn_endpoint_returns_assistant_response() -> None:
    client = TestClient(create_app())
    episode_id = create_episode_and_return_id(client)

    response = client.post("/api/turns", json={"episode_id": episode_id, "text": "Привет"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["assistant_response"] == "Понял. Можем обсудить это подробнее."
    assert payload["fallback_count"] == 0
    assert payload["runtime_result"] is None


def test_api_response_contains_fallback_count() -> None:
    client = TestClient(create_app())
    episode_id = create_episode_and_return_id(client)

    response = client.post("/api/turns", json={"episode_id": episode_id, "text": "Привет"})

    assert response.status_code == 200
    payload = response.json()
    assert "fallback_count" in payload
    assert payload["fallback_count"] == 0


def test_turn_endpoint_missing_episode_id_returns_422() -> None:
    client = TestClient(create_app())

    response = client.post("/api/turns", json={"text": "Привет"})

    assert response.status_code == 422


def test_turn_endpoint_missing_text_returns_422() -> None:
    client = TestClient(create_app())
    episode_id = create_episode_and_return_id(client)

    response = client.post("/api/turns", json={"episode_id": episode_id})

    assert response.status_code == 422


def test_turn_endpoint_persists_episode_state() -> None:
    episode_repository = InMemoryEpisodeRepository()
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="rule_update",
            items=(
                MessageItem(
                    type="rule_candidate",
                    text="Показывай понимание",
                    scope="all_tasks",
                    key="show_understanding_before_execution",
                ),
            ),
        )
    )
    client = TestClient(
        create_app(
            classifier=classifier,
            episode_repository=episode_repository,
        )
    )
    episode_id = create_episode_and_return_id(client)

    response = client.post("/api/turns", json={"episode_id": episode_id, "text": "Показывай понимание"})

    assert response.status_code == 200
    assert response.json()["episode_state"] == "pending_rule_review"
    stored_episode = episode_repository.get_by_id(episode_id)
    assert stored_episode is not None
    assert stored_episode.state == "pending_rule_review"


def test_turn_endpoint_handles_cancel_text() -> None:
    client = TestClient(create_app())
    episode_id = create_episode_and_return_id(client)

    response = client.post("/api/turns", json={"episode_id": episode_id, "text": "отмена"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["episode_state"] == "cancelled"
    assert payload["fallback_count"] == 0
    assert payload["assistant_response"] == "Эпизод отменён."


def test_api_fallback_increments_fallback_count() -> None:
    client = TestClient(create_app())
    episode_id = create_episode_and_return_id(client)

    response = client.post(
        "/api/turns",
        json={"episode_id": episode_id, "text": "/ambiguous Сделай что-нибудь хорошее"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["fallback_count"] == 1


def test_api_second_fallback_returns_fallback_count_2() -> None:
    client = TestClient(create_app())
    episode_id = create_episode_and_return_id(client)

    first_response = client.post(
        "/api/turns",
        json={"episode_id": episode_id, "text": "/ambiguous Сделай что-нибудь хорошее"},
    )
    assert first_response.status_code == 200

    second_response = client.post(
        "/api/turns",
        json={"episode_id": episode_id, "text": "/ambiguous Сделай что-нибудь хорошее"},
    )

    assert second_response.status_code == 200
    payload = second_response.json()
    assert payload["fallback_count"] == 2


def test_api_successful_turn_resets_fallback_count() -> None:
    client = TestClient(create_app())
    episode_id = create_episode_and_return_id(client)

    fallback_response = client.post(
        "/api/turns",
        json={"episode_id": episode_id, "text": "/ambiguous Сделай что-нибудь хорошее"},
    )
    assert fallback_response.status_code == 200
    assert fallback_response.json()["fallback_count"] == 1

    success_response = client.post("/api/turns", json={"episode_id": episode_id, "text": "/query"})

    assert success_response.status_code == 200
    assert success_response.json()["fallback_count"] == 0


def test_api_task_pending_understanding_resets_fallback_count() -> None:
    client = TestClient(create_app())
    episode_id = create_episode_and_return_id(client)

    fallback_response = client.post(
        "/api/turns",
        json={"episode_id": episode_id, "text": "/ambiguous Сделай что-нибудь хорошее"},
    )
    assert fallback_response.status_code == 200
    assert fallback_response.json()["fallback_count"] == 1

    rule_response = client.post("/api/turns", json={"episode_id": episode_id, "text": "/rule Показывай понимание"})
    assert rule_response.status_code == 200

    confirm_rule_response = client.post("/api/turns", json={"episode_id": episode_id, "text": "да"})
    assert confirm_rule_response.status_code == 200

    task_response = client.post("/api/turns", json={"episode_id": episode_id, "text": "/task Проверить код"})

    assert task_response.status_code == 200
    payload = task_response.json()
    assert payload["episode_state"] == "pending_understanding_review"
    assert payload["fallback_count"] == 0


def test_turn_endpoint_default_chat_intake_message_id_matches_user_message() -> None:
    client = TestClient(create_app())
    episode_id = create_episode_and_return_id(client)

    response = client.post("/api/turns", json={"episode_id": episode_id, "text": "Привет"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["intake_result"] is not None
    assert payload["intake_result"]["message_id"]
    assert payload["intake_result"]["message_id"] != "default-chat"


def test_api_default_classifier_can_create_rule_candidate_with_slash_rule() -> None:
    client = TestClient(create_app())
    episode_id = create_episode_and_return_id(client)

    response = client.post("/api/turns", json={"episode_id": episode_id, "text": "/rule Показывай понимание"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["episode_state"] == "pending_rule_review"
    assert payload["rule_candidate"] is not None


def test_api_rule_confirm_da_updates_program_version() -> None:
    client = TestClient(create_app())
    episode_id = create_episode_and_return_id(client)

    create_rule_response = client.post(
        "/api/turns",
        json={"episode_id": episode_id, "text": "/rule Показывай понимание"},
    )
    assert create_rule_response.status_code == 200
    assert create_rule_response.json()["program_version"] == 1

    confirm_response = client.post("/api/turns", json={"episode_id": episode_id, "text": "да"})

    assert confirm_response.status_code == 200
    payload = confirm_response.json()
    assert payload["episode_state"] == "open"
    assert payload["program_version"] == 2
    assert "подтверждено" in payload["assistant_response"].lower()


def test_api_rule_reject_net_does_not_update_program_version() -> None:
    client = TestClient(create_app())
    episode_id = create_episode_and_return_id(client)

    create_rule_response = client.post(
        "/api/turns",
        json={"episode_id": episode_id, "text": "/rule Показывай понимание"},
    )
    assert create_rule_response.status_code == 200
    assert create_rule_response.json()["program_version"] == 1

    reject_response = client.post("/api/turns", json={"episode_id": episode_id, "text": "нет"})

    assert reject_response.status_code == 200
    payload = reject_response.json()
    assert payload["episode_state"] == "open"
    assert payload["program_version"] == 1
    assert "отклонено" in payload["assistant_response"].lower()


def test_turn_response_contract_contains_required_fields() -> None:
    client = TestClient(create_app())
    episode_id = create_episode_and_return_id(client)

    response = client.post("/api/turns", json={"episode_id": episode_id, "text": "Привет"})

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "episode_id",
        "episode_state",
        "fallback_count",
        "assistant_response",
        "intake_result",
        "runtime_result",
        "rule_candidate",
        "pending_switch_decision",
        "unknown_utterance",
        "program_version",
    }


def test_program_current_endpoint_returns_contract() -> None:
    client = TestClient(create_app())

    response = client.get("/api/program/current")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_version"] == 1
    assert "enforced_rules" in payload
    assert "future_rules" in payload
    assert "policies" in payload


def test_api_response_is_json_serializable() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    client = TestClient(create_app(classifier=classifier))
    episode_id = create_episode_and_return_id(client)

    response = client.post("/api/turns", json={"episode_id": episode_id, "text": "Проверить код"})

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    assert payload["runtime_result"]["status"] == "completed"
    assert payload["runtime_result"]["execution_mode"] == "stub"
    assert payload["runtime_result"]["did_execute_real_work"] is False
    assert payload["runtime_result"]["verification_result"]["verified"] is True


def test_api_runtime_result_exposes_stub_execution_mode() -> None:
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="task",
            items=(MessageItem(type="task", text="Проверить код"),),
        )
    )
    client = TestClient(create_app(classifier=classifier))
    episode_id = create_episode_and_return_id(client)

    response = client.post("/api/turns", json={"episode_id": episode_id, "text": "Проверить код"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime_result"]["execution_mode"] == "stub"
    assert payload["runtime_result"]["did_execute_real_work"] is False


def test_serialize_value_handles_tuple_and_list() -> None:
    serialized = serialize_value({"items": ("a", "b"), "nested": ["c", "d"]})

    assert serialized == {"items": ["a", "b"], "nested": ["c", "d"]}


def test_api_does_not_import_from_domain_into_wrong_layer() -> None:
    for path in (
        "src/jeeves_dap/domain/agent_program.py",
        "src/jeeves_dap/domain/models.py",
        "src/jeeves_dap/domain/validation.py",
    ):
        with open(path, encoding="utf-8") as file:
            source = file.read()

        assert "jeeves_dap.api" not in source


def test_no_ui_files_added() -> None:
    ui_extensions = {".tsx", ".ts", ".jsx", ".js", ".css", ".html"}
    repo_files = Path(".").rglob("*")
    ui_files = [
        str(path)
        for path in repo_files
        if path.is_file() and path.suffix in ui_extensions and "src/jeeves_dap/api.py" not in str(path)
    ]

    assert ui_files == []


def test_no_keyword_router_added() -> None:
    with open("src/jeeves_dap/api.py", encoding="utf-8") as file:
        source = file.read()

    assert "LLMClassifier" not in source
    assert "KeywordClassifier" not in source


def test_api_existing_endpoints_still_pass() -> None:
    client = TestClient(create_app())
    episode_response = client.post("/api/episodes")
    assert episode_response.status_code == 200
    episode_id = episode_response.json()["episode_id"]

    turn_response = client.post("/api/turns", json={"episode_id": episode_id, "text": "Привет"})
    assert turn_response.status_code == 200

    health_response = client.get("/api/health")
    assert health_response.status_code == 200

    program_response = client.get("/api/program/current")
    assert program_response.status_code == 200


def test_api_wires_rule_candidate_repository() -> None:
    episode_repository = InMemoryEpisodeRepository()
    rule_candidate_repository = InMemoryRuleCandidateRepository()
    classifier = StubClassifier(
        default_result=IntakeResult(
            message_id="m1",
            primary_intent="rule_update",
            items=(
                MessageItem(
                    type="rule_candidate",
                    text="Показывай понимание",
                    scope="all_tasks",
                    key="show_understanding_before_execution",
                ),
            ),
        )
    )
    client = TestClient(
        create_app(
            classifier=classifier,
            episode_repository=episode_repository,
            rule_candidate_repository=rule_candidate_repository,
        )
    )
    episode_id = create_episode_and_return_id(client)

    response = client.post("/api/turns", json={"episode_id": episode_id, "text": "Показывай понимание"})

    assert response.status_code == 200
    assert rule_candidate_repository.get_by_episode_id(episode_id) is not None


def test_api_wires_pending_understanding_repository() -> None:
    episode_repository = InMemoryEpisodeRepository()
    pending_understanding_repository = InMemoryPendingUnderstandingRepository()
    client = TestClient(
        create_app(
            episode_repository=episode_repository,
            pending_understanding_repository=pending_understanding_repository,
        )
    )
    episode_id = create_episode_and_return_id(client)

    client.post("/api/turns", json={"episode_id": episode_id, "text": "/rule Показывай понимание"})
    client.post("/api/turns", json={"episode_id": episode_id, "text": "да"})
    response = client.post("/api/turns", json={"episode_id": episode_id, "text": "/task Проверить код"})

    assert response.status_code == 200
    assert pending_understanding_repository.get_by_episode_id(episode_id) is not None


def test_api_manual_flow_rule_then_task_then_da_executes_runtime() -> None:
    client = TestClient(create_app())
    episode_id = create_episode_and_return_id(client)

    rule_response = client.post("/api/turns", json={"episode_id": episode_id, "text": "/rule Показывай понимание"})
    assert rule_response.status_code == 200
    assert rule_response.json()["episode_state"] == "pending_rule_review"

    confirm_rule_response = client.post("/api/turns", json={"episode_id": episode_id, "text": "да"})
    assert confirm_rule_response.status_code == 200
    assert confirm_rule_response.json()["program_version"] == 2

    task_response = client.post("/api/turns", json={"episode_id": episode_id, "text": "/task Проверить код"})
    assert task_response.status_code == 200
    task_payload = task_response.json()
    assert task_payload["episode_state"] == "pending_understanding_review"
    assert task_payload["runtime_result"] is None

    confirm_understanding_response = client.post("/api/turns", json={"episode_id": episode_id, "text": "да"})
    assert confirm_understanding_response.status_code == 200
    confirm_payload = confirm_understanding_response.json()
    assert confirm_payload["episode_state"] == "open"
    assert confirm_payload["runtime_result"] is not None
    assert confirm_payload["runtime_result"]["status"] == "completed"
    assert confirm_payload["runtime_result"]["execution_mode"] == "stub"
    assert confirm_payload["runtime_result"]["did_execute_real_work"] is False
    assert "stub-результат" in confirm_payload["assistant_response"]


def test_api_manual_flow_returns_stub_honest_result() -> None:
    client = TestClient(create_app())
    episode_id = create_episode_and_return_id(client)

    client.post("/api/turns", json={"episode_id": episode_id, "text": "/rule Показывай понимание"})
    client.post("/api/turns", json={"episode_id": episode_id, "text": "да"})
    client.post("/api/turns", json={"episode_id": episode_id, "text": "/task Проверить код"})
    confirm_understanding_response = client.post("/api/turns", json={"episode_id": episode_id, "text": "да"})

    assert confirm_understanding_response.status_code == 200
    payload = confirm_understanding_response.json()
    assert payload["runtime_result"]["execution_mode"] == "stub"
    assert payload["runtime_result"]["did_execute_real_work"] is False
    assert "stub-результат" in payload["assistant_response"]


def test_no_ui_buttons_added() -> None:
    client = TestClient(create_app())

    response = client.get("/")
    html = response.text.lower()

    assert "<button" not in html


def test_no_llm_or_keyword_router_added() -> None:
    with open("src/jeeves_dap/api.py", encoding="utf-8") as file:
        source = file.read()

    assert "LLMClassifier" not in source
    assert "KeywordClassifier" not in source
