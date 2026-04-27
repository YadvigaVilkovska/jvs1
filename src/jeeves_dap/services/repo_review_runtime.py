"""Contract: deterministic read-only repository review runtime without repository mutations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import subprocess

STATUS_SHORT_COMMAND = ("git", "status", "--short")
STATUS_COMMAND = ("git", "status")
RECENT_COMMITS_COMMAND = ("git", "log", "--oneline", "-5")
DIFF_NAMES_COMMAND = ("git", "diff", "--name-only")
DIFF_SCOPED_COMMAND = ("git", "diff", "--", "src", "tests", "scripts", ".env.example", ".gitignore")
UNTRACKED_COMMAND = ("git", "ls-files", "--others", "--exclude-standard")
READ_AGENTS_COMMAND = ("cat", "AGENTS.md")
TYPE_IGNORE_PATTERN = "type" + ": " + "ignore"
MOJIBAKE_PATTERN = "\\|".join(
    (
        chr(0x03A9),
        chr(0x00B5),
        chr(0x00E6),
        chr(0x00C7),
        chr(0x221E),
    )
)
TYPE_IGNORE_SCAN_COMMAND = (
    "grep",
    "-R",
    "-n",
    "--include=*.py",
    TYPE_IGNORE_PATTERN,
    "src",
    "tests",
    "scripts",
)
MOJIBAKE_SCAN_COMMAND = (
    "grep",
    "-R",
    "-n",
    "--include=*.py",
    MOJIBAKE_PATTERN,
    "src",
    "tests",
    "scripts",
)

REPO_REVIEW_TASKS = frozenset(
    {
        "проверить репозиторий",
        "проверь репозиторий",
        "проверить текущий репозиторий",
        "проверь текущий репозиторий",
        "review repository",
        "review current repository",
    }
)


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Contract: one captured read-only command result used for repository review reports."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[tuple[str, ...], Path], CommandResult]


class RepoReviewRuntime:
    """Contract: execute one fixed read-only review sequence and build a repository report."""

    def __init__(self, command_runner: CommandRunner | None = None, repo_root: Path | None = None) -> None:
        self._command_runner = command_runner or self._run_command
        self._repo_root = repo_root or Path(__file__).resolve().parents[3]

    def is_repo_review_task(self, goal: str) -> bool:
        """Contract: return whether a normalized goal maps to the explicit repo review runtime."""

        return _normalize_goal(goal) in REPO_REVIEW_TASKS

    def review_repository(self) -> tuple[str, bool]:
        """Contract: run allowed read-only commands and return report text plus verdict flag."""

        status_short = self._command_runner(STATUS_SHORT_COMMAND, self._repo_root)
        status_full = self._command_runner(STATUS_COMMAND, self._repo_root)
        recent_commits = self._command_runner(RECENT_COMMITS_COMMAND, self._repo_root)
        diff_names = self._command_runner(DIFF_NAMES_COMMAND, self._repo_root)
        diff_scoped = self._command_runner(DIFF_SCOPED_COMMAND, self._repo_root)
        type_ignore_result = self._command_runner(TYPE_IGNORE_SCAN_COMMAND, self._repo_root)
        mojibake_result = self._command_runner(MOJIBAKE_SCAN_COMMAND, self._repo_root)
        untracked_result = self._command_runner(UNTRACKED_COMMAND, self._repo_root)
        agents_result = self._command_runner(READ_AGENTS_COMMAND, self._repo_root)

        has_type_ignore = type_ignore_result.returncode == 0
        has_mojibake = mojibake_result.returncode == 0
        verdict_ok = not has_type_ignore and not has_mojibake
        verdict = "OK" if verdict_ok else "Needs attention"

        report = "\n".join(
            [
                "Read-only repository review completed. Файлы не изменялись.",
                f"Verdict: {verdict}",
                "",
                "Changed files:",
                _safe_block(status_short.stdout or "(none)"),
                "",
                "Git status summary:",
                _safe_block(status_full.stdout),
                "",
                "Recent commits:",
                _safe_block(recent_commits.stdout),
                "",
                "Git diff names:",
                _safe_block(diff_names.stdout or "(none)"),
                "",
                "Scoped diff summary:",
                _safe_block(diff_scoped.stdout or "(none)"),
                "",
                "Untracked files:",
                _safe_block(untracked_result.stdout or "(none)"),
                "",
                "Safety checks:",
                _safe_block(
                    "\n".join(
                        [
                            f"type_ignore: {'found' if has_type_ignore else 'not found'}",
                            f"mojibake: {'found' if has_mojibake else 'not found'}",
                        ]
                    )
                ),
                "",
                "AGENTS.md summary:",
                _safe_block(agents_result.stdout.splitlines()[0] if agents_result.stdout else "(empty)"),
            ]
        )
        return report, verdict_ok

    @staticmethod
    def _run_command(command: tuple[str, ...], cwd: Path) -> CommandResult:
        """Contract: execute one allowed read-only command and capture stdout/stderr only."""

        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        return CommandResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
        )


def _normalize_goal(goal: str) -> str:
    """Contract: normalize goal text for exact repo review matching only."""

    return " ".join(goal.strip().lower().split())


def _safe_block(text: str) -> str:
    """Contract: return a non-empty text block for report rendering."""

    return text if text.strip() else "(empty)"
