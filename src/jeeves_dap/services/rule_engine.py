"""Contract: build inspectable runtime plans from active program policies only."""

from __future__ import annotations

from jeeves_dap.domain.models import AgentProgram, RuntimePlan, RuntimeStep, RuntimeTask


class RuleEngine:
    """Contract: translate supported enforced policies into runtime plan steps."""

    def build_runtime_plan(
        self,
        task: RuntimeTask,
        active_program: AgentProgram,
        *,
        include_show_understanding_step: bool = True,
    ) -> RuntimePlan:
        """Build a runtime plan where only supported enforced policies affect execution order."""

        steps: list[RuntimeStep] = []

        if (
            active_program.communication_policy.show_understanding_before_execution
            and include_show_understanding_step
        ):
            steps.append(
                RuntimeStep(
                    type="show_understanding",
                    requires_confirmation=True,
                    reason="active_rule: show_understanding_before_execution",
                )
            )

        steps.append(
            RuntimeStep(
                type="execute_task_stub",
                requires_confirmation=False,
            )
        )

        if active_program.verification_policy.must_check_success_condition:
            steps.append(
                RuntimeStep(
                    type="verify_success_condition",
                    requires_confirmation=False,
                    reason="baseline_policy: must_check_success_condition",
                )
            )

        return RuntimePlan(steps=tuple(steps))
