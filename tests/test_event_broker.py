"""Unit tests for Event Broker, Node State Streaming, and Dashboard Telemetry."""

import asyncio
import unittest
from agentic_workflow.core.events import WorkflowEvent, WorkflowEventListener, WorkflowEventType
from agentic_workflow.domain.models import NodeStatus
from agentic_workflow.domain.state import AgentWorkflowState
from agentic_workflow.gateway.event_broker import InMemoryAsyncEventBroker
from agentic_workflow.gateway.listeners.dashboard import DashboardTelemetryListener
from agentic_workflow.gateway.listeners.streaming import NodeStateStreamListener
from agentic_workflow.nodes.base import GraphNode


class SimpleNode(GraphNode[AgentWorkflowState]):
    async def _on_execute(self, state: AgentWorkflowState) -> dict:
        return {"step_count": 1}


class TestEventBrokerAndListeners(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.broker = InMemoryAsyncEventBroker()
        await self.broker.start()

    async def asyncTearDown(self):
        await self.broker.stop()

    async def test_node_publishes_events_to_broker(self):
        # 1. Setup listeners
        stream_listener = NodeStateStreamListener()
        dashboard_listener = DashboardTelemetryListener()

        self.broker.subscribe(stream_listener)
        self.broker.subscribe(dashboard_listener)

        # 2. Attach broker to node
        node = SimpleNode(name="worker_node", event_broker=self.broker)
        state: AgentWorkflowState = {"thread_id": "job-101"}

        # 3. Execute node
        await node(state)

        # Allow dispatch loop to process
        await asyncio.sleep(0.05)

        # 4. Verify Dashboard captured metrics
        metrics = dashboard_listener.get_job_metrics("job-101")
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics.current_node, "worker_node")
        self.assertEqual(metrics.nodes_executed, 1)
        self.assertGreaterEqual(metrics.total_duration_ms, 0.0)

    async def test_node_state_streaming_consumption(self):
        stream_listener = NodeStateStreamListener()
        self.broker.subscribe(stream_listener)

        # Publish simulated lifecycle events
        thread_id = "stream-thread-99"
        await self.broker.publish(
            WorkflowEvent(
                event_type=WorkflowEventType.NODE_ENTERED,
                thread_id=thread_id,
                node_name="planner",
                to_status=NodeStatus.RUNNING,
            )
        )
        await self.broker.publish(
            WorkflowEvent(
                event_type=WorkflowEventType.NODE_STATE_CHANGED,
                thread_id=thread_id,
                node_name="planner",
                from_status=NodeStatus.RUNNING,
                to_status=NodeStatus.EVALUATING,
            )
        )
        await self.broker.publish(
            WorkflowEvent(
                event_type=WorkflowEventType.GRAPH_COMPLETED,
                thread_id=thread_id,
            )
        )

        # Allow broker to dispatch
        await asyncio.sleep(0.05)

        # Consume from stream
        received_events = []
        async for event in stream_listener.stream_events(thread_id, replay_history=True):
            received_events.append(event)

        self.assertEqual(len(received_events), 3)
        self.assertEqual(received_events[0].event_type, WorkflowEventType.NODE_ENTERED)
        self.assertEqual(received_events[1].event_type, WorkflowEventType.NODE_STATE_CHANGED)
        self.assertEqual(received_events[1].to_status, NodeStatus.EVALUATING)
        self.assertEqual(received_events[2].event_type, WorkflowEventType.GRAPH_COMPLETED)

    async def test_dashboard_active_jobs_and_error_tracking(self):
        dashboard_listener = DashboardTelemetryListener()
        self.broker.subscribe(dashboard_listener)

        thread_id = "job-error-test"
        await self.broker.publish(
            WorkflowEvent(
                event_type=WorkflowEventType.NODE_ENTERED,
                thread_id=thread_id,
                node_name="db_query",
                to_status=NodeStatus.RUNNING,
            )
        )
        await self.broker.publish(
            WorkflowEvent(
                event_type=WorkflowEventType.NODE_STATE_CHANGED,
                thread_id=thread_id,
                node_name="db_query",
                from_status=NodeStatus.RUNNING,
                to_status=NodeStatus.FAILED,
                message="Connection refused to replica DB",
            )
        )

        await asyncio.sleep(0.05)

        metrics = dashboard_listener.get_job_metrics(thread_id)
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics.error_message, "Connection refused to replica DB")
        self.assertIn("db_query", [e["node_name"] for e in metrics.recent_events])


if __name__ == "__main__":
    unittest.main()
