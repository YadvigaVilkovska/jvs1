"""Contract: stub runtime executor proving rule-driven plan changes without real execution."""

from __future__ import annotations

from jeeves_dap.domain.models import AgentProgram, RuntimeResult, RuntimeTask
from jeeves_dap.services.repo_review_runtime import RepoReviewRuntime
from jeeves_dap.services.rule_engine import RuleEngine
from jeeves_dap.services.verifier_stub import VerifierStub

STUB_RESULT_TEXT = (
    "Это stub-результат: реальное выполнение задачи не запускалось. "
    "Система только показала симулированный результат MVP."
)
TASK_CLARIFICATION_RESPONSE_TEXT = "Что именно нужно сделать? Опишите задачу одним коротким предложением."
SHOW_UNDERSTANDING_RULE = "show_understanding_before_execution"
VAGUE_TASKS = frozenset({"сделай нормально", "сделай красиво", "переделай", "fix it", "make it better"})
WRITE_ORIENTED_TASKS = frozenset({"исправь это", "почини проект"})


class TaskRuntimeStub:
    """Contract: build a runtime plan, return a stub result, and run stub verification."""

    def __init__(
        self,
        rule_engine: RuleEngine,
        verifier: VerifierStub,
        repo_review_runtime: RepoReviewRuntime | None = None,
    ) -> None:
        self._rule_engine = rule_engine
        self._verifier = verifier
        self._repo_review_runtime = repo_review_runtime or RepoReviewRuntime()

    def requires_clarification(self, task: RuntimeTask) -> bool:
        """Contract: return whether the runtime must refuse and ask one clarification question."""

        normalized_goal = _normalize_task_goal(task.goal)
        return normalized_goal in VAGUE_TASKS or normalized_goal in WRITE_ORIENTED_TASKS

    def clarification_response(self) -> str:
        """Contract: return one clarification question when execution would be unsafe."""

        return TASK_CLARIFICATION_RESPONSE_TEXT

    def execute(
        self,
        task: RuntimeTask,
        active_program: AgentProgram,
        *,
        include_show_understanding_step: bool = True,
    ) -> RuntimeResult:
        """Execute a task as a pure stub with rule-driven plan construction and verification."""

        runtime_plan = self._rule_engine.build_runtime_plan(
            task,
            active_program,
            include_show_understanding_step=include_show_understanding_step,
        )
        applied_rules = (
            (SHOW_UNDERSTANDING_RULE,)
            if any(step.type == "show_understanding" for step in runtime_plan.steps)
            else ()
        )
        if self._repo_review_runtime.is_repo_review_task(task.goal):
            report_text, verdict_ok = self._repo_review_runtime.review_repository()
            status = "completed" if verdict_ok else "failed"
            verification_result = self._verifier.verify_status(
                task,
                status,
                "read_only_repo_review",
            )
            return RuntimeResult(
                task_id=task.id,
                status=status,
                execution_mode="read_only_repo_review",
                did_execute_real_work=True,
                result_text=report_text,
                applied_rules=applied_rules,
                runtime_plan=runtime_plan,
                verification_result=verification_result,
            )

        status = "completed"
        verification_result = self._verifier.verify_status(task, status, "stub")

        return RuntimeResult(
            task_id=task.id,
            status=status,
            execution_mode="stub",
            did_execute_real_work=False,
            result_text=STUB_RESULT_TEXT,
            applied_rules=applied_rules,
            runtime_plan=runtime_plan,
            verification_result=verification_result,
        )


def _normalize_task_goal(goal: str) -> str:
    """Contract: normalize task text for exact safe routing decisions."""

    return " ".join(goal.strip().lower().split())
