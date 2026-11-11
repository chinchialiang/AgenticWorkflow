"""Base abstraction and Template Method Pattern for all workflow nodes."""

import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Generic, Optional, TypeVar

from agentic_workflow.core.events import EventBroker, WorkflowEvent, WorkflowEventType
from agentic_workflow.domain.models import NodeExecutionRecord, NodeStatus

logger = logging.getLogger("agentic_workflow.nodes")

TState = TypeVar("TState")

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore


class GraphNode(ABC, Generic[TState]):
    """Abstract base class for all nodes enforcing lifecycle logging,
    state machine transitions, and decoupled event publishing.
    """

    def __init__(self, name: str, event_broker: Optional[EventBroker] = None):
        self.name = name
        self.current_status: NodeStatus = NodeStatus.PENDING
        self.event_broker: Optional[EventBroker] = event_broker
        self._current_thread_id: str = "default"

    def set_event_broker(self, broker: EventBroker) -> None:
        """Injects or configures the event broker."""
        self.event_broker = broker

    async def __call__(self, state: TState, config: Optional[RunnableConfig] = None) -> dict[str, Any]:
        """Template Method: Governs entering, executing, exiting, and event publishing."""
        # Extract thread_id if available in state or LangGraph config
        if isinstance(state, dict) and state.get("thread_id"):
            self._current_thread_id = str(state["thread_id"])
        elif config and isinstance(config, dict):
            cfg = config.get("configurable", {})
            if "thread_id" in cfg:
                self._current_thread_id = str(cfg["thread_id"])

        start_perf = time.perf_counter()
        started_at = datetime.now(timezone.utc)

        # 1. Enter node
        await self._publish_event(
            WorkflowEventType.NODE_ENTERED,
            to_status=NodeStatus.RUNNING,
            message=f"Node '{self.name}' entered execution.",
        )
        await self._transition_to(NodeStatus.RUNNING, message=f"Node '{self.name}' entered execution.")

        try:
            # 2. Execute subclass-specific business logic
            delta = await self._on_execute(state)

            # 3. Complete execution
            completed_at = datetime.now(timezone.utc)
            duration_ms = round((time.perf_counter() - start_perf) * 1000, 2)

            await self._transition_to(
                NodeStatus.SUCCEEDED,
                duration_ms=duration_ms,
                message=f"Node '{self.name}' completed successfully.",
            )
            await self._publish_event(
                WorkflowEventType.NODE_EXITED,
                to_status=NodeStatus.SUCCEEDED,
                duration_ms=duration_ms,
                message=f"Node '{self.name}' exited successfully.",
            )

            # 4. Create audit record
            record = NodeExecutionRecord(
                node_name=self.name,
                status=NodeStatus.SUCCEEDED,
                duration_ms=duration_ms,
                started_at=started_at,
                completed_at=completed_at,
            )

            # 5. Enrich delta with audit trail and node metadata
            return self._enrich_delta(delta, record)

        except Exception as exc:
            completed_at = datetime.now(timezone.utc)
            duration_ms = round((time.perf_counter() - start_perf) * 1000, 2)

            await self._transition_to(
                NodeStatus.FAILED,
                duration_ms=duration_ms,
                error=str(exc),
                message=f"Node '{self.name}' failed with unhandled exception.",
            )
            await self._publish_event(
                WorkflowEventType.NODE_EXITED,
                to_status=NodeStatus.FAILED,
                duration_ms=duration_ms,
                message=f"Node '{self.name}' exited with failure: {exc}",
            )

            record = NodeExecutionRecord(
                node_name=self.name,
                status=NodeStatus.FAILED,
                duration_ms=duration_ms,
                started_at=started_at,
                completed_at=completed_at,
                error_message=str(exc),
            )

            fallback_delta = {
                "error_message": str(exc),
                "current_node": self.name,
                "node_execution_history": record,
            }
            return fallback_delta

    @abstractmethod
    async def _on_execute(self, state: TState) -> dict[str, Any]:
        """Subclasses implement pure business logic here."""
        pass

    async def _transition_to(
        self,
        new_status: NodeStatus,
        message: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """Transitions node lifecycle status, emits structured log, and publishes event."""
        old_status = self.current_status
        self.current_status = new_status

        log_payload = {
            "event": "NODE_STATE_CHANGED",
            "node_name": self.name,
            "from_status": old_status.value,
            "to_status": new_status.value,
            "message": message or f"Transitioned from {old_status.value} to {new_status.value}",
            **extra,
        }

        if new_status == NodeStatus.FAILED:
            logger.error(json.dumps(log_payload))
        elif new_status == NodeStatus.RETRYING:
            logger.warning(json.dumps(log_payload))
        else:
            logger.info(json.dumps(log_payload))

        # Publish asynchronous decoupled event
        await self._publish_event(
            WorkflowEventType.NODE_STATE_CHANGED,
            from_status=old_status,
            to_status=new_status,
            message=message,
            payload=extra,
        )

    async def _publish_event(
        self,
        event_type: WorkflowEventType,
        from_status: Optional[NodeStatus] = None,
        to_status: Optional[NodeStatus] = None,
        duration_ms: Optional[float] = None,
        message: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        """Helper to dispatch event to the broker if configured."""
        if self.event_broker:
            event = WorkflowEvent(
                event_type=event_type,
                thread_id=self._current_thread_id,
                node_name=self.name,
                from_status=from_status,
                to_status=to_status,
                duration_ms=duration_ms,
                message=message,
                payload=payload or {},
            )
            await self.event_broker.publish(event)

    def _enrich_delta(
        self,
        delta: Optional[dict[str, Any]],
        record: NodeExecutionRecord,
    ) -> dict[str, Any]:
        result = dict(delta or {})
        result["current_node"] = self.name
        result["node_execution_history"] = record
        return result
