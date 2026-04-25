"""Contract: stub verifier for PR-5 runtime proof without side effects."""

from __future__ import annotations

from jeeves_dap.domain.models import RuntimeResult, RuntimeTask, VerificationResult


class VerifierStub:
    """Contract: verify stub task results using explicit or derived success conditions."""

    def verify_status(self, task: RuntimeTask, status: str) -> VerificationResult:
        """Return a verification result using a task plus final status only."""

        checked_success_condition = (
            task.success_condition
            if task.success_condition is not None
            else f"Пользователь получил результат по запросу: {task.goal}"
        )

        return VerificationResult(
            verified=status == "completed",
            checked_success_condition=checked_success_condition,
        )

    def verify_result(self, task: RuntimeTask, result: RuntimeResult) -> VerificationResult:
        """Return a verification result for an already constructed runtime result."""

        return self.verify_status(task, result.status)
