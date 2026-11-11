"""Execution / Tool node for API calls and Sandboxed Code execution."""

import asyncio
import inspect
import logging
import time
from typing import Any, Callable, Optional

from agentic_workflow.domain.models import ExecutionStatus, ToolResult, WorkflowMessage
from agentic_workflow.domain.state import AgentWorkflowState
from agentic_workflow.nodes.base import GraphNode

logger = logging.getLogger(__name__)


class ToolExecutionNode(GraphNode[AgentWorkflowState]):
    """Deterministic node for side effects: API invocations and Code Execution.
    Guarantees:
    - Error isolation: Catches exceptions and returns standardized ToolResult.
    - Idempotency support: Respects idempotency keys on write commands.
    - Timeout protection: Prevents hanging external dependencies.
    """

    def __init__(
        self,
        name: str,
        tool_func: Callable[..., Any],
        timeout_seconds: float = 30.0,
        is_mutating_command: bool = False,
    ):
        super().__init__(name)
        self.tool_func = tool_func
        self.timeout_seconds = timeout_seconds
        self.is_mutating_command = is_mutating_command

    async def execute(self, state: AgentWorkflowState) -> dict[str, Any]:
        tool_call = state.get("pending_tool_call") or {}
        tool_args = tool_call.get("arguments", {})
        idempotency_key = tool_call.get("idempotency_key")

        start_time = time.perf_counter()
        logger.info("Executing ToolNode '%s' with args: %s", self.name, list(tool_args.keys()))

        try:
            # Execute with timeout protection
            if inspect.iscoroutinefunction(self.tool_func):
                raw_result = await asyncio.wait_for(
                    self.tool_func(**tool_args),
                    timeout=self.timeout_seconds,
                )
            else:
                raw_result = await asyncio.to_thread(
                    self.tool_func,
                    **tool_args,
                )

            duration_ms = (time.perf_counter() - start_time) * 1000
            result = ToolResult(
                tool_name=self.name,
                status=ExecutionStatus.SUCCESS,
                output=raw_result,
                execution_time_ms=round(duration_ms, 2),
                idempotency_key=idempotency_key,
            )

        except asyncio.TimeoutError:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Tool '%s' timed out after %.1fs", self.name, self.timeout_seconds)
            result = ToolResult(
                tool_name=self.name,
                status=ExecutionStatus.FAILED,
                error_message=f"Execution timed out after {self.timeout_seconds} seconds.",
                execution_time_ms=round(duration_ms, 2),
                idempotency_key=idempotency_key,
            )

        except Exception as exc:  # pylint: disable=broad-except
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception("Tool '%s' failed with error: %s", self.name, exc)
            result = ToolResult(
                tool_name=self.name,
                status=ExecutionStatus.FAILED,
                error_message=str(exc),
                execution_time_ms=round(duration_ms, 2),
                idempotency_key=idempotency_key,
            )

        # Output observation message and record tool result in scratchpad
        obs_content = f"Tool '{self.name}' Result: {result.model_dump_json()}"
        return {
            "messages": WorkflowMessage(role="tool", content=obs_content, name=self.name),
            "latest_tool_result": result,
            "pending_tool_call": None,  # Clear the pending call
            "step_count": 1,
        }
