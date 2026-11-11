"""Unit tests for Node Lifecycle FSM and Audit Logging."""

import unittest
from agentic_workflow.domain.models import NodeStatus, WorkflowMessage
from agentic_workflow.domain.state import AgentWorkflowState
from agentic_workflow.gateway.llm import MockLLMInvoker
from agentic_workflow.nodes.base import GraphNode
from agentic_workflow.nodes.cognitive import CognitiveNode
from agentic_workflow.nodes.execution import ToolExecutionNode


class DummyNode(GraphNode[AgentWorkflowState]):
    async def _on_execute(self, state: AgentWorkflowState) -> dict:
        return {"step_count": 1}


class FailingNode(GraphNode[AgentWorkflowState]):
    async def _on_execute(self, state: AgentWorkflowState) -> dict:
        raise RuntimeError("Fatal node failure")


class TestNodeLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_template_method_success_audit_record(self):
        node = DummyNode(name="dummy_test_node")
        state: AgentWorkflowState = {"step_count": 0}

        delta = await node(state)

        # Verify audit record is attached automatically by Template Method
        self.assertIn("node_execution_history", delta)
        record = delta["node_execution_history"]
        self.assertEqual(record.node_name, "dummy_test_node")
        self.assertEqual(record.status, NodeStatus.SUCCEEDED)
        self.assertGreaterEqual(record.duration_ms, 0.0)
        self.assertEqual(delta["current_node"], "dummy_test_node")

    async def test_template_method_exception_handling(self):
        node = FailingNode(name="failing_test_node")
        state: AgentWorkflowState = {}

        delta = await node(state)

        # Verify error is captured gracefully in the audit record without crashing
        self.assertIn("node_execution_history", delta)
        record = delta["node_execution_history"]
        self.assertEqual(record.node_name, "failing_test_node")
        self.assertEqual(record.status, NodeStatus.FAILED)
        self.assertIn("Fatal node failure", record.error_message)

    async def test_tool_node_lifecycle_waiting_external(self):
        def sample_tool():
            return "tool_output"

        tool_node = ToolExecutionNode(name="my_api", tool_func=sample_tool)
        delta = await tool_node({"pending_tool_call": {"name": "my_api", "arguments": {}}})

        record = delta["node_execution_history"]
        self.assertEqual(record.status, NodeStatus.SUCCEEDED)
        self.assertEqual(tool_node.current_status, NodeStatus.SUCCEEDED)


if __name__ == "__main__":
    unittest.main()
