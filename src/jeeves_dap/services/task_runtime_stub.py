"""Contract: stub runtime executor proving rule-driven plan changes without real execution."""

from __future__ import annotations

from jeeves_dap.domain.models import AgentProgram, RuntimeResult, RuntimeTask
from jeeves_dap.services.rule_engine import RuleEngine
from jeeves_dap.services.verifier_stub import VerifierStub

STUB_RESULT_TEXT = (
    "Это stub-результат: реальное выполнение задачи не запускалось. "
    "Система только показала симулированный результат MVP."
)
SHOW_UNDERSTANDING_RULE = "show_understanding_before_execution"


class TaskRuntimeStub:
    """Contract: build a runtime plan, return a stub result, and run stub verification."""

    def __init__(self, rule_engine: RuleEngine, verifier: VerifierStub) -> None:
        self._rule_engine = rule_engine
        self._verifier = verifier

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
        status = "completed"
        verification_result = self._verifier.verify_status(task, status)

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
