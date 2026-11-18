"""Domain models, value objects, and evaluation contracts."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """Lifecycle status for workflow execution."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    SUCCESS = "SUCCESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class NodeStatus(str, Enum):
    """Micro-lifecycle status for an individual node execution."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    EVALUATING = "EVALUATING"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    RETRYING = "RETRYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class NodeExecutionRecord(BaseModel):
    """Audit trail record of a single node execution."""
    node_name: str
    status: NodeStatus
    duration_ms: float
    started_at: datetime
    completed_at: datetime
    attempt: int = 1
    error_message: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DoDResult(BaseModel):
    """Result of Definition of Done (DoD) evaluation."""
    is_met: bool = Field(..., description="True if the output satisfies all acceptance criteria.")
    score: float = Field(default=1.0, ge=0.0, le=1.0, description="Evaluation confidence or quality score.")
    feedback: list[str] = Field(default_factory=list, description="Actionable feedback if DoD failed.")


class ToolResult(BaseModel):
    """Standardized result for API and Code execution nodes."""
    tool_name: str
    status: ExecutionStatus
    output: Any = None
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0
    idempotency_key: Optional[str] = None


@dataclass(frozen=True)
class WorkflowMessage:
    """Immutable representation of a message in the workflow log."""
    role: str
    content: str
    name: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMUsage(BaseModel):
    """Standardized token and cost telemetry returned by LLM invokers."""
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    model_id: Optional[str] = None


class LLMResponse(BaseModel):
    """Normalized response envelope from an LLM gateway invoker."""
    content: Any
    usage: LLMUsage = Field(default_factory=LLMUsage)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
