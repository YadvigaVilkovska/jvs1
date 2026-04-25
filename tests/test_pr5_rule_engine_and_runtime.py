"""Contract: PR-5 regression tests for RuleEngine, TaskRuntimeStub, and VerifierStub."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from jeeves_dap.domain.models import RuntimeTask
from jeeves_dap.repositories.agent_program_repository import InMemoryAgentProgramVersionRepository
from jeeves_dap.services.agent_program_service import AgentProgramService
from jeeves_dap.services.rule_engine import RuleEngine
from jeeves_dap.services.task_runtime_stub import TaskRuntimeStub
from jeeves_dap.services.verifier_stub import VerifierStub


def test_rule_engine_default_plan_executes_and_verifies() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    engine = RuleEngine()
    task = RuntimeTask(id="t1", goal="Проверить код")

    plan = engine.build_runtime_plan(task, version.program)

    assert [step.type for step in plan.steps] == [
        "execute_task_stub",
        "verify_success_condition",
    ]


def test_rule_engine_show_understanding_step_first_when_policy_true() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    patched_program = replace(
        version.program,
        communication_policy=replace(
            version.program.communication_policy,
            show_understanding_before_execution=True,
        ),
    )
    engine = RuleEngine()

    plan = engine.build_runtime_plan(RuntimeTask(id="t1", goal="Проверить код"), patched_program)

    assert plan.steps[0].type == "show_understanding"
    assert plan.steps[0].requires_confirmation is True


def test_rule_engine_no_show_understanding_when_policy_false() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    engine = RuleEngine()

    plan = engine.build_runtime_plan(RuntimeTask(id="t1", goal="Проверить код"), version.program)

    assert all(step.type != "show_understanding" for step in plan.steps)


def test_rule_engine_future_rules_do_not_affect_plan() -> None:
    repository = InMemoryAgentProgramVersionRepository()
    service = AgentProgramService(repository)
    v1 = service.create_initial_version("v1", datetime.now(UTC))
    future_candidate = service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m1",
        source_episode_id="e1",
        text="Всегда добавляй список багов",
        key="always_add_bug_list",
        scope="code_review",
    )
    v2 = service.confirm_rule_candidate(
        active_version=v1,
        candidate=future_candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )
    engine = RuleEngine()

    plan = engine.build_runtime_plan(RuntimeTask(id="t1", goal="Проверить код"), v2.program)

    assert [step.type for step in plan.steps] == [
        "execute_task_stub",
        "verify_success_condition",
    ]


def test_rule_engine_includes_verify_step_when_policy_true() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    engine = RuleEngine()

    plan = engine.build_runtime_plan(RuntimeTask(id="t1", goal="Проверить код"), version.program)

    assert any(step.type == "verify_success_condition" for step in plan.steps)


def test_verifier_uses_default_success_condition_when_missing() -> None:
    verifier = VerifierStub()
    task = RuntimeTask(id="t1", goal="Проверить код")

    verification = verifier.verify_status(task, "completed")

    assert verification.checked_success_condition == "Пользователь получил результат по запросу: Проверить код"


def test_verifier_returns_false_for_non_completed_result() -> None:
    verifier = VerifierStub()
    task = RuntimeTask(id="t1", goal="Проверить код", success_condition="Код проверен")

    verification = verifier.verify_status(task, "failed")

    assert verification.verified is False
    assert verification.checked_success_condition == "Код проверен"


def test_task_runtime_stub_returns_completed_result() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    runtime = TaskRuntimeStub(RuleEngine(), VerifierStub())

    result = runtime.execute(RuntimeTask(id="t1", goal="Проверить код"), version.program)

    assert result.status == "completed"
    assert result.result_text == "Фиктивный результат выполнения задачи."
    assert result.verification_result.verified is True


def test_task_runtime_stub_constructs_result_with_real_verification_result() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    runtime = TaskRuntimeStub(RuleEngine(), VerifierStub())

    result = runtime.execute(RuntimeTask(id="t1", goal="Проверить код"), version.program)

    assert result.verification_result is not None
    assert result.verification_result.checked_success_condition == (
        "Пользователь получил результат по запросу: Проверить код"
    )


def test_task_runtime_stub_reports_applied_show_understanding_rule() -> None:
    repository = InMemoryAgentProgramVersionRepository()
    service = AgentProgramService(repository)
    v1 = service.create_initial_version("v1", datetime.now(UTC))
    candidate = service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m1",
        source_episode_id="e1",
        text="Показывай понимание",
        key="show_understanding_before_execution",
        scope="all_tasks",
    )
    v2 = service.confirm_rule_candidate(
        active_version=v1,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )
    runtime = TaskRuntimeStub(RuleEngine(), VerifierStub())

    result = runtime.execute(RuntimeTask(id="t1", goal="Проверить код"), v2.program)

    assert result.applied_rules == ("show_understanding_before_execution",)
    assert result.runtime_plan.steps[0].type == "show_understanding"


def test_task_runtime_stub_does_not_apply_future_rule() -> None:
    repository = InMemoryAgentProgramVersionRepository()
    service = AgentProgramService(repository)
    v1 = service.create_initial_version("v1", datetime.now(UTC))
    candidate = service.create_rule_candidate(
        candidate_id="c1",
        source_message_id="m1",
        source_episode_id="e1",
        text="Всегда добавляй список багов",
        key="always_add_bug_list",
        scope="code_review",
    )
    v2 = service.confirm_rule_candidate(
        active_version=v1,
        candidate=candidate,
        new_version_id="v2",
        new_rule_id="r1",
        created_at=datetime.now(UTC),
    )
    runtime = TaskRuntimeStub(RuleEngine(), VerifierStub())

    result = runtime.execute(RuntimeTask(id="t1", goal="Проверить код"), v2.program)

    assert result.applied_rules == ()
    assert all(step.type != "show_understanding" for step in result.runtime_plan.steps)


def test_domain_layer_does_not_import_services_or_repositories() -> None:
    for path in (
        "src/jeeves_dap/domain/agent_program.py",
        "src/jeeves_dap/domain/models.py",
        "src/jeeves_dap/domain/validation.py",
    ):
        with open(path, encoding="utf-8") as file:
            source = file.read()

        assert "jeeves_dap.services" not in source
        assert "jeeves_dap.repositories" not in source


def test_runtime_code_has_no_type_ignore_comments() -> None:
    forbidden_marker = "type" + ": " + "ignore"

    for path in (
        "src/jeeves_dap/services/task_runtime_stub.py",
        "src/jeeves_dap/services/verifier_stub.py",
        "tests/test_pr5_rule_engine_and_runtime.py",
    ):
        with open(path, encoding="utf-8") as file:
            source = file.read()

        assert forbidden_marker not in source
