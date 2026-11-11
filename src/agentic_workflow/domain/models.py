"""Domain models, value objects, and evaluation contracts."""

from dataclasses import dataclass, field
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
