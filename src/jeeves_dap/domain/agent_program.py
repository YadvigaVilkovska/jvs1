"""Contract: default agent program factory and rule registry for the domain layer."""

from __future__ import annotations

from jeeves_dap.domain.models import (
    AgentProgram,
    CommunicationPolicy,
    MemoryPolicy,
    ToolPolicy,
    VerificationPolicy,
)

KNOWN_RULE_KEYS: frozenset[str] = frozenset({"show_understanding_before_execution"})


def build_default_agent_program_v1() -> AgentProgram:
    """Contract: build the exact MVP default program snapshot for version 1."""

    return AgentProgram(
        rules=(),
        communication_policy=CommunicationPolicy(
            show_understanding_before_execution=False,
        ),
        memory_policy=MemoryPolicy(
            enabled=False,
            retention="episode",
        ),
        tool_policy=ToolPolicy(
            allowed_tools=(),
            require_approval_for_side_effects=False,
            side_effects_supported=False,
        ),
        verification_policy=VerificationPolicy(
            must_check_success_condition=True,
            default_success_condition_mode="completed_status_is_success",
        ),
    )
