"""Routing functions and transition guards (Enterprise Integration Patterns)."""

import logging
from typing import Literal

from agentic_workflow.domain.models import ExecutionStatus
from agentic_workflow.domain.state import AgentWorkflowState

logger = logging.getLogger(__name__)


def evaluate_transition(
    state: AgentWorkflowState,
    max_steps: int = 25,
) -> Literal["human_approval", "tool_execution", "evaluator", "end", "error_handler"]:
    """Deterministic Content-Based Router guarding transitions:
    1. Circuit breaker on max step transitions
    2. Failure escalation check
    3. Human-in-the-loop approval gate
    4. Pending tool execution routing
    5. Normal termination
    """
    current_steps = state.get("step_count", 0)
    configured_max = state.get("max_steps") or max_steps

    # 1. Circuit breaker: runaway execution protection
    if current_steps >= configured_max:
        logger.warning("Circuit breaker triggered: step_count (%d) reached max_steps (%d)", current_steps, configured_max)
        return "error_handler"

    # 2. Check for unrecoverable failure
    if state.get("execution_status") == ExecutionStatus.FAILED:
        return "error_handler"

    # 3. Human-in-the-loop governance
    if state.get("requires_approval", False):
        logger.info("Human approval required before proceeding.")
        return "human_approval"

    # 4. Tool execution route
    if state.get("pending_tool_call"):
        return "tool_execution"

    # 5. Completed successfully
    if state.get("execution_status") == ExecutionStatus.COMPLETED:
        return "end"

    return "evaluator"
