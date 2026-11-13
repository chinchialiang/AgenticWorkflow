"""Three-tier workflow state definition."""

from typing import Annotated, Any, Sequence
from typing_extensions import TypedDict

from agentic_workflow.domain.models import ExecutionStatus, NodeExecutionRecord, ToolResult, WorkflowMessage
from agentic_workflow.domain.reducers import (
    append_execution_record,
    append_messages,
    increment_counter,
    last_value,
    merge_dicts,
)


class AgentWorkflowState(TypedDict, total=False):
    """Canonical graph state conforming to the 3-tier namespace design:
    1. Domain Payload: Core business data
    2. Workflow Control State: Orchestration metadata & governance flags
    3. Transient Scratchpad: Temporary reasoning and tool results
    """

    # --- 1. Domain Payload (Append-only message log & business artifacts) ---
    messages: Annotated[Sequence[WorkflowMessage], append_messages]
    artifacts: Annotated[dict[str, Any], merge_dicts]

    # --- 2. Workflow Control State (FSM guards, engine telemetry & audit trail) ---
    thread_id: str
    execution_status: Annotated[ExecutionStatus, last_value]
    step_count: Annotated[int, increment_counter]
    max_steps: int
    requires_approval: bool
    current_node: Annotated[str, last_value]
    error_message: Annotated[str | None, last_value]
    node_execution_history: Annotated[Sequence[NodeExecutionRecord], append_execution_record]

    # --- 3. Transient Scratchpad (Cleared or compacted across phases) ---
    pending_tool_call: dict[str, Any] | None
    latest_tool_result: ToolResult | None
    dod_evaluation: dict[str, Any] | None
