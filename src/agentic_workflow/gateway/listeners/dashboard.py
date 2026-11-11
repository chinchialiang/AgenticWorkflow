"""Dashboard Telemetry Listener for operational observability."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from agentic_workflow.core.events import WorkflowEvent, WorkflowEventListener, WorkflowEventType
from agentic_workflow.domain.models import NodeStatus


class JobMetrics(BaseModel):
    """Real-time operational snapshot of a single workflow execution."""
    thread_id: str
    status: str = "PENDING"
    current_node: Optional[str] = None
    nodes_executed: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_duration_ms: float = 0.0
    recent_events: List[dict[str, Any]] = Field(default_factory=list)
    error_message: Optional[str] = None


class DashboardTelemetryListener(WorkflowEventListener):
    """Maintains an in-memory operational dashboard of all active and past workflow jobs."""

    def __init__(self, max_recent_events_per_job: int = 20):
        self._max_recent_events = max_recent_events_per_job
        self._jobs: Dict[str, JobMetrics] = {}

    async def on_event(self, event: WorkflowEvent) -> None:
        thread_id = event.thread_id
        if thread_id not in self._jobs:
            self._jobs[thread_id] = JobMetrics(thread_id=thread_id, started_at=event.timestamp)

        job = self._jobs[thread_id]

        # Update metrics based on event type
        if event.event_type == WorkflowEventType.GRAPH_STARTED:
            job.status = "RUNNING"
            job.started_at = event.timestamp

        elif event.event_type == WorkflowEventType.NODE_ENTERED:
            job.current_node = event.node_name
            job.status = "RUNNING"

        elif event.event_type == WorkflowEventType.NODE_STATE_CHANGED:
            job.current_node = event.node_name
            if event.to_status == NodeStatus.FAILED:
                job.error_message = event.message or "Node failed"

        elif event.event_type == WorkflowEventType.NODE_EXITED:
            job.nodes_executed += 1
            if event.duration_ms:
                job.total_duration_ms += event.duration_ms

        elif event.event_type == WorkflowEventType.GRAPH_SUSPENDED:
            job.status = "SUSPENDED"

        elif event.event_type == WorkflowEventType.GRAPH_COMPLETED:
            job.status = "COMPLETED"
            job.completed_at = event.timestamp

        elif event.event_type == WorkflowEventType.GRAPH_FAILED:
            job.status = "FAILED"
            job.completed_at = event.timestamp
            job.error_message = event.message or "Workflow failed"

        # Keep a bounded log of recent events
        job.recent_events.append({
            "event_type": event.event_type.value,
            "node_name": event.node_name,
            "timestamp": event.timestamp.isoformat(),
            "message": event.message,
        })
        if len(job.recent_events) > self._max_recent_events:
            job.recent_events.pop(0)

    def get_job_metrics(self, thread_id: str) -> Optional[JobMetrics]:
        """Retrieves metrics for a specific workflow thread."""
        return self._jobs.get(thread_id)

    def list_all_jobs(self) -> List[JobMetrics]:
        """Lists metrics for all registered workflow threads."""
        return list(self._jobs.values())

    def list_active_jobs(self) -> List[JobMetrics]:
        """Lists currently running or suspended jobs."""
        return [j for j in self._jobs.values() if j.status in ("RUNNING", "SUSPENDED")]
