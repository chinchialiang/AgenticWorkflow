"""Hello World single-node workflow demonstrating LangGraph execution,
Node lifecycle logging, and Event Listener observability.
"""

import asyncio
import logging
import sys

from agentic_workflow.core.events import WorkflowEvent, WorkflowEventType
from agentic_workflow.core.graph import WorkflowGraphBuilder
from agentic_workflow.domain.models import ExecutionStatus, WorkflowMessage
from agentic_workflow.domain.state import AgentWorkflowState
from agentic_workflow.gateway.event_broker import InMemoryAsyncEventBroker
from agentic_workflow.gateway.listeners.dashboard import DashboardTelemetryListener
from agentic_workflow.gateway.listeners.streaming import NodeStateStreamListener
from agentic_workflow.nodes.base import GraphNode

# Configure root logger so node structured JSON logs appear clearly on stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


class HelloWorldNode(GraphNode[AgentWorkflowState]):
    """A minimal node that prints 'Hello World!! LangGraph' and updates workflow state."""

    async def _on_execute(self, state: AgentWorkflowState) -> dict:
        greeting = "Hello World!! LangGraph"
        
        # 1. Print the core action
        print("\n" + "=" * 50)
        print(f"  >>> ACTION: {greeting}")
        print("=" * 50 + "\n")

        # 2. Return state delta
        return {
            "messages": WorkflowMessage(
                role="assistant",
                content=greeting,
                name=self.name,
            ),
            "artifacts": {"greeting": greeting},
            "execution_status": ExecutionStatus.COMPLETED,
        }


async def main():
    print("\n--- [Step 1] Initializing Event Broker and Listeners ---")
    broker = InMemoryAsyncEventBroker()
    await broker.start()

    # 1. Register Stream Listener (Simulates SSE/WebSocket client)
    stream_listener = NodeStateStreamListener()
    broker.subscribe(stream_listener)

    # 2. Register Dashboard Telemetry Listener (Job monitor)
    dashboard_listener = DashboardTelemetryListener()
    broker.subscribe(dashboard_listener)

    print("--- [Step 2] Building Workflow Topology with LangGraph ---")
    builder = WorkflowGraphBuilder(event_broker=broker)
    hello_node = HelloWorldNode(name="hello_world_node")

    builder.add_node(hello_node)
    builder.set_entry_point("hello_world_node")
    builder.add_edge("hello_world_node", "END")

    # Compile to native LangGraph executable
    app = builder.compile_langgraph()

    thread_id = "hello-thread-20261111"
    initial_state: AgentWorkflowState = {
        "step_count": 0,
        "max_steps": 5,
        "artifacts": {},
    }

    print(f"--- [Step 3] Executing Workflow (thread_id='{thread_id}') ---")
    await broker.publish(
        WorkflowEvent(
            event_type=WorkflowEventType.GRAPH_STARTED,
            thread_id=thread_id,
            message="Workflow started.",
        )
    )

    # Native LangGraph invocation
    config = {"configurable": {"thread_id": thread_id}}
    # Merge thread_id into state for the node template method
    run_state = {**initial_state, "thread_id": thread_id}
    final_state = await app.ainvoke(run_state, config=config)

    await broker.publish(
        WorkflowEvent(
            event_type=WorkflowEventType.GRAPH_COMPLETED,
            thread_id=thread_id,
            message="Workflow completed.",
        )
    )

    # Allow async event dispatch loop to finish processing
    await asyncio.sleep(0.1)

    print("--- [Step 4] Verifying Listener & Telemetry Outputs ---")

    # A. Verify Dashboard Listener metrics
    metrics = dashboard_listener.get_job_metrics(thread_id)
    print("\n[Dashboard Telemetry Metrics]:")
    if metrics:
        print(f"  - Job Status:          {metrics.status}")
        print(f"  - Total Nodes Run:     {metrics.nodes_executed}")
        print(f"  - Total Duration (ms): {metrics.total_duration_ms} ms")
        print(f"  - Recent Events Count: {len(metrics.recent_events)}")

    # B. Verify Stream Listener events (replaying historical stream)
    print("\n[Stream Listener Captured Events]:")
    async for event in stream_listener.stream_events(thread_id, replay_history=True):
        print(f"  -> [{event.event_type.value}] Node='{event.node_name}' | From='{event.from_status}' -> To='{event.to_status}' | Msg='{event.message}'")

    # C. Verify In-State Audit History
    print("\n[State Execution Audit History]:")
    history = final_state.get("node_execution_history", [])
    for rec in history:
        print(f"  - Node: {rec.node_name} | Status: {rec.status} | Latency: {rec.duration_ms}ms")

    # D. Verify Final Domain State
    print("\n[Final State Artifacts]:", final_state.get("artifacts"))

    await broker.stop()
    print("\n--- Verification Complete! ---")


if __name__ == "__main__":
    asyncio.run(main())
