"""Base abstraction and Template Method Pattern for all workflow nodes."""

import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Generic, Optional, TypeVar

from agentic_workflow.domain.models import NodeExecutionRecord, NodeStatus

logger = logging.getLogger("agentic_workflow.nodes")

TState = TypeVar("TState")


class GraphNode(ABC, Generic[TState]):
    """Abstract base class for all nodes enforcing lifecycle logging & state machine transitions.
    Implements the Template Method Pattern.
    """

    def __init__(self, name: str):
        self.name = name
        self.current_status: NodeStatus = NodeStatus.PENDING

    async def __call__(self, state: TState) -> dict[str, Any]:
        """Template Method: Governs entering, executing, exiting, and audit logging."""
        start_perf = time.perf_counter()
        started_at = datetime.now(timezone.utc)
        self._transition_to(NodeStatus.RUNNING, message=f"Node '{self.name}' entered execution.")

        try:
            # 1. Execute subclass-specific business logic
            delta = await self._on_execute(state)

            # 2. Complete execution
            completed_at = datetime.now(timezone.utc)
            duration_ms = round((time.perf_counter() - start_perf) * 1000, 2)
            self._transition_to(
                NodeStatus.SUCCEEDED,
                duration_ms=duration_ms,
                message=f"Node '{self.name}' completed successfully.",
            )

            # 3. Create audit record
            record = NodeExecutionRecord(
                node_name=self.name,
                status=NodeStatus.SUCCEEDED,
                duration_ms=duration_ms,
                started_at=started_at,
                completed_at=completed_at,
            )

            # 4. Enrich delta with audit trail and node metadata
            return self._enrich_delta(delta, record)

        except Exception as exc:
            completed_at = datetime.now(timezone.utc)
            duration_ms = round((time.perf_counter() - start_perf) * 1000, 2)
            self._transition_to(
                NodeStatus.FAILED,
                duration_ms=duration_ms,
                error=str(exc),
                message=f"Node '{self.name}' failed with unhandled exception.",
            )

            record = NodeExecutionRecord(
                node_name=self.name,
                status=NodeStatus.FAILED,
                duration_ms=duration_ms,
                started_at=started_at,
                completed_at=completed_at,
                error_message=str(exc),
            )

            # In enterprise workflows, attach failure record to state rather than crashing unhandled
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

    def _transition_to(
        self,
        new_status: NodeStatus,
        message: Optional[str] = None,
        **extra: Any,
    ) -> None:
        """Transitions node lifecycle status and emits a structured log event."""
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

        # Level selection based on status
        if new_status == NodeStatus.FAILED:
            logger.error(json.dumps(log_payload))
        elif new_status == NodeStatus.RETRYING:
            logger.warning(json.dumps(log_payload))
        else:
            logger.info(json.dumps(log_payload))

    def _enrich_delta(
        self,
        delta: Optional[dict[str, Any]],
        record: NodeExecutionRecord,
    ) -> dict[str, Any]:
        result = dict(delta or {})
        result["current_node"] = self.name
        result["node_execution_history"] = record
        return result
