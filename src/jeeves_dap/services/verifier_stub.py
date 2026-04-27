"""Contract: stub verifier for PR-5 runtime proof without side effects."""

from __future__ import annotations

from jeeves_dap.domain.models import RuntimeResult, RuntimeTask, VerificationResult


class VerifierStub:
    """Contract: verify stub task results using explicit or derived success conditions."""

    def verify_status(self, task: RuntimeTask, status: str, execution_mode: str = "stub") -> VerificationResult:
        """Return a verification result using a task plus final status only."""

        checked_success_condition = (
            task.success_condition
            if task.success_condition is not None
            else _default_success_condition(task.goal, execution_mode)
        )

        return VerificationResult(
            verified=status == "completed",
            checked_success_condition=checked_success_condition,
        )

    def verify_result(self, task: RuntimeTask, result: RuntimeResult) -> VerificationResult:
        """Return a verification result for an already constructed runtime result."""

        return self.verify_status(task, result.status, result.execution_mode)


def _default_success_condition(goal: str, execution_mode: str) -> str:
    """Contract: return an honest default success condition for each execution mode."""

    if execution_mode == "read_only_repo_review":
        return f"Пользователь получил read-only отчёт по репозиторию без изменения файлов: {goal}"
    return f"Пользователь получил stub-результат без реального выполнения: {goal}"
