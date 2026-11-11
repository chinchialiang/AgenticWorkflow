"""Event contracts and listener interfaces for workflow observability and streaming."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional, Sequence
import uuid
from pydantic import BaseModel, Field

from agentic_workflow.domain.models import NodeStatus


class WorkflowEventType(str, Enum):
    """Categorized workflow and node lifecycle events."""
    # Graph-level events
    GRAPH_STARTED = "GRAPH_STARTED"
    GRAPH_SUSPENDED = "GRAPH_SUSPENDED"  # HITL approval pause
    GRAPH_RESUMED = "GRAPH_RESUMED"
    GRAPH_COMPLETED = "GRAPH_COMPLETED"
    GRAPH_FAILED = "GRAPH_FAILED"

    # Node-level micro-lifecycle events
    NODE_ENTERED = "NODE_ENTERED"
    NODE_STATE_CHANGED = "NODE_STATE_CHANGED"
    NODE_EXITED = "NODE_EXITED"

    # Streaming events
    TOKEN_STREAMED = "TOKEN_STREAMED"


class WorkflowEvent(BaseModel):
    """Standardized event contract dispatched across the system."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: WorkflowEventType
    thread_id: str = "default"
    trace_id: Optional[str] = None
    node_name: Optional[str] = None
    from_status: Optional[NodeStatus] = None
    to_status: Optional[NodeStatus] = None
    duration_ms: Optional[float] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None


class WorkflowEventListener(ABC):
    """Abstract interface for all event listeners (Observer Pattern)."""

    @abstractmethod
    async def on_event(self, event: WorkflowEvent) -> None:
        """Handle an incoming workflow event asynchronously."""
        pass


class EventBroker(ABC):
    """Abstract broker interface decoupled from concrete messaging infrastructure
    (Supports in-memory, Redis Pub/Sub, Kafka, RabbitMQ).
    """

    @abstractmethod
    async def publish(self, event: WorkflowEvent) -> None:
        """Publishes an event to all interested subscribers."""
        pass

    @abstractmethod
    def subscribe(
        self,
        listener: WorkflowEventListener,
        event_types: Optional[Sequence[WorkflowEventType]] = None,
    ) -> None:
        """Subscribes a listener to receive events (optionally filtered by type)."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Starts any background workers or connection pools."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully shuts down the broker."""
        pass
