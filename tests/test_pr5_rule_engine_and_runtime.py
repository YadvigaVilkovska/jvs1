"""Contract: PR-5 regression tests for RuleEngine, TaskRuntimeStub, and VerifierStub."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
import subprocess

from jeeves_dap.domain.models import RuntimeTask
from jeeves_dap.repositories.agent_program_repository import InMemoryAgentProgramVersionRepository
from jeeves_dap.services.agent_program_service import AgentProgramService
from jeeves_dap.services.repo_review_runtime import CommandResult, RepoReviewRuntime
from jeeves_dap.services.rule_engine import RuleEngine
from jeeves_dap.services.task_runtime_stub import TaskRuntimeStub
from jeeves_dap.services.verifier_stub import VerifierStub


def build_repo_review_runtime_runner(*, type_ignore_returncode: int = 1):
    """Contract: create a deterministic read-only command runner for repo-review tests."""

    calls: list[tuple[str, ...]] = []
    type_ignore_pattern = "type" + ": " + "ignore"
    mojibake_pattern = "\\|".join(
        (
            chr(0x03A9),
            chr(0x00B5),
            chr(0x00E6),
            chr(0x00C7),
            chr(0x221E),
        )
    )

    def runner(command: tuple[str, ...], cwd: Path) -> CommandResult:
        del cwd
        calls.append(command)
        type_ignore_stdout = f"src/example.py:1:{type_ignore_pattern}" if type_ignore_returncode == 0 else ""
        outputs = {
            ("git", "status", "--short"): (" M src/jeeves_dap/services/task_runtime_stub.py", "", 0),
            ("git", "status"): ("On branch main\nChanges not staged for commit:", "", 0),
            ("git", "log", "--oneline", "-5"): ("abc123 latest\nfff111 previous", "", 0),
            ("git", "diff", "--name-only"): ("src/jeeves_dap/services/task_runtime_stub.py", "", 0),
            (
                "git",
                "diff",
                "--",
                "src",
                "tests",
                "scripts",
                ".env.example",
                ".gitignore",
            ): ("diff --git a/src/jeeves_dap/services/task_runtime_stub.py b/src/jeeves_dap/services/task_runtime_stub.py", "", 0),
            ("grep", "-R", "-n", "--include=*.py", type_ignore_pattern, "src", "tests", "scripts"): (
                type_ignore_stdout,
                "",
                type_ignore_returncode,
            ),
            ("grep", "-R", "-n", "--include=*.py", mojibake_pattern, "src", "tests", "scripts"): ("", "", 1),
            ("git", "ls-files", "--others", "--exclude-standard"): ("", "", 0),
            ("cat", "AGENTS.md"): ("# AGENTS.md — Jeeves DAP Codex Operating Rules", "", 0),
        }
        stdout, stderr, returncode = outputs[command]
        return CommandResult(
            command=command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    return runner, calls


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

    assert verification.checked_success_condition == (
        "Пользователь получил stub-результат без реального выполнения: Проверить код"
    )


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
    assert result.execution_mode == "stub"
    assert result.did_execute_real_work is False
    assert result.result_text == (
        "Это stub-результат: реальное выполнение задачи не запускалось. "
        "Система только показала симулированный результат MVP."
    )
    assert result.verification_result.verified is True


def test_task_runtime_stub_reports_stub_execution_mode() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    runtime = TaskRuntimeStub(RuleEngine(), VerifierStub())

    result = runtime.execute(RuntimeTask(id="t1", goal="Проверить код"), version.program)

    assert result.execution_mode == "stub"


def test_task_runtime_stub_did_not_execute_real_work() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    runtime = TaskRuntimeStub(RuleEngine(), VerifierStub())

    result = runtime.execute(RuntimeTask(id="t1", goal="Проверить код"), version.program)

    assert result.did_execute_real_work is False


def test_task_runtime_stub_result_text_is_honest() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    runtime = TaskRuntimeStub(RuleEngine(), VerifierStub())

    result = runtime.execute(RuntimeTask(id="t1", goal="Проверить код"), version.program)

    assert "stub-результат" in result.result_text
    assert "реальное выполнение задачи не запускалось" in result.result_text


def test_task_runtime_stub_constructs_result_with_real_verification_result() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    runtime = TaskRuntimeStub(RuleEngine(), VerifierStub())

    result = runtime.execute(RuntimeTask(id="t1", goal="Проверить код"), version.program)

    assert result.verification_result is not None
    assert result.verification_result.checked_success_condition == (
        "Пользователь получил stub-результат без реального выполнения: Проверить код"
    )


def test_verifier_checks_stub_success_condition_not_real_task() -> None:
    verifier = VerifierStub()
    task = RuntimeTask(id="t1", goal="Проверить код")

    verification = verifier.verify_status(task, "completed")

    assert "stub-результат" in verification.checked_success_condition
    assert "без реального выполнения" in verification.checked_success_condition


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


def test_repo_review_task_is_not_stub() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    runner, _ = build_repo_review_runtime_runner()
    runtime = TaskRuntimeStub(
        RuleEngine(),
        VerifierStub(),
        RepoReviewRuntime(command_runner=runner, repo_root=Path.cwd()),
    )

    result = runtime.execute(RuntimeTask(id="t1", goal="Проверить репозиторий"), version.program)

    assert result.execution_mode == "read_only_repo_review"
    assert result.did_execute_real_work is True


def test_repo_review_runtime_does_not_modify_files() -> None:
    before = subprocess.run(
        ("git", "status", "--short"),
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    runner, _ = build_repo_review_runtime_runner()
    runtime = TaskRuntimeStub(
        RuleEngine(),
        VerifierStub(),
        RepoReviewRuntime(command_runner=runner, repo_root=Path.cwd()),
    )

    runtime.execute(RuntimeTask(id="t1", goal="Проверить репозиторий"), version.program)

    after = subprocess.run(
        ("git", "status", "--short"),
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    assert before == after


def test_repo_review_result_mentions_read_only() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    runner, _ = build_repo_review_runtime_runner()
    runtime = TaskRuntimeStub(
        RuleEngine(),
        VerifierStub(),
        RepoReviewRuntime(command_runner=runner, repo_root=Path.cwd()),
    )

    result = runtime.execute(RuntimeTask(id="t1", goal="Проверь репозиторий"), version.program)

    assert "Read-only repository review completed" in result.result_text
    assert "Файлы не изменялись" in result.result_text


def test_repo_review_result_contains_git_status() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    runner, _ = build_repo_review_runtime_runner()
    runtime = TaskRuntimeStub(
        RuleEngine(),
        VerifierStub(),
        RepoReviewRuntime(command_runner=runner, repo_root=Path.cwd()),
    )

    result = runtime.execute(RuntimeTask(id="t1", goal="Проверь репозиторий"), version.program)

    assert "Git status summary:" in result.result_text
    assert "Changes not staged for commit" in result.result_text


def test_repo_review_result_contains_recent_commits() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    runner, _ = build_repo_review_runtime_runner()
    runtime = TaskRuntimeStub(
        RuleEngine(),
        VerifierStub(),
        RepoReviewRuntime(command_runner=runner, repo_root=Path.cwd()),
    )

    result = runtime.execute(RuntimeTask(id="t1", goal="Review repository"), version.program)

    assert "Recent commits:" in result.result_text
    assert "abc123 latest" in result.result_text


def test_repo_review_result_omits_external_check_result() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    runner, calls = build_repo_review_runtime_runner()
    runtime = TaskRuntimeStub(
        RuleEngine(),
        VerifierStub(),
        RepoReviewRuntime(command_runner=runner, repo_root=Path.cwd()),
    )

    result = runtime.execute(RuntimeTask(id="t1", goal="Review current repository"), version.program)

    assert "Check result from ./scripts/check.sh:" not in result.result_text
    assert ("./scripts/check.sh",) not in calls


def test_repo_review_failed_verdict_returns_failed_status() -> None:
    service = AgentProgramService(InMemoryAgentProgramVersionRepository())
    version = service.create_initial_version("v1", datetime.now(UTC))
    runner, _ = build_repo_review_runtime_runner(type_ignore_returncode=0)
    runtime = TaskRuntimeStub(
        RuleEngine(),
        VerifierStub(),
        RepoReviewRuntime(command_runner=runner, repo_root=Path.cwd()),
    )

    result = runtime.execute(RuntimeTask(id="t1", goal="Review current repository"), version.program)

    assert result.status == "failed"
    assert result.verification_result.verified is False
    assert "Verdict: Needs attention" in result.result_text


def test_repo_review_forbidden_commands_are_not_used() -> None:
    source = Path("src/jeeves_dap/services/repo_review_runtime.py").read_text(encoding="utf-8")

    assert '"git", "add"' not in source
    assert '"git", "commit"' not in source
    assert '"git", "push"' not in source
    assert '"git", "restore"' not in source
    assert '"git", "checkout"' not in source
    assert '"git", "reset"' not in source
    assert '"rm"' not in source
    assert '"mv"' not in source


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
