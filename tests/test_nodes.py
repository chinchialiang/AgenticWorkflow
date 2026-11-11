"""Unit tests for CognitiveNode and ToolExecutionNode."""

import asyncio
import unittest
from pydantic import BaseModel

from agentic_workflow.domain.models import DoDResult, ExecutionStatus, WorkflowMessage
from agentic_workflow.domain.state import AgentWorkflowState
from agentic_workflow.gateway.llm import MockLLMInvoker
from agentic_workflow.nodes.cognitive import CognitiveNode
from agentic_workflow.nodes.execution import ToolExecutionNode


class PlanOutput(BaseModel):
    steps: list[str]
    confidence: float


class TestNodes(unittest.IsolatedAsyncioTestCase):
    async def test_cognitive_node_success_with_dod(self):
        # 1. Setup mock returning valid JSON conforming to PlanOutput
        mock_invoker = MockLLMInvoker(
            canned_response='{"steps": ["step 1", "step 2"], "confidence": 0.95}'
        )

        def dod_eval(output: PlanOutput, state: AgentWorkflowState) -> DoDResult:
            if len(output.steps) >= 2:
                return DoDResult(is_met=True, score=1.0)
            return DoDResult(is_met=False, feedback=["At least 2 steps required"])

        node = CognitiveNode(
            name="planner_node",
            system_prompt="You are a senior planner.",
            llm_invoker=mock_invoker,
            output_schema=PlanOutput,
            dod_evaluator=dod_eval,
        )

        initial_state: AgentWorkflowState = {
            "messages": [WorkflowMessage(role="user", content="Plan the migration")],
        }

        delta = await node(initial_state)

        self.assertEqual(delta["dod_evaluation"]["status"], "PASSED")
        self.assertEqual(delta["execution_status"], ExecutionStatus.RUNNING)
        self.assertEqual(delta["current_node"], "planner_node")
        self.assertEqual(mock_invoker.invocation_count, 1)

    async def test_cognitive_node_self_correction_loop(self):
        # 1st response fails DoD (only 1 step), 2nd response satisfies DoD (2 steps)
        responses = [
            '{"steps": ["only one step"], "confidence": 0.5}',
            '{"steps": ["step 1", "step 2"], "confidence": 0.9}',
        ]
        mock_invoker = MockLLMInvoker(canned_response=lambda count: responses[count - 1])

        def dod_eval(output: PlanOutput, state: AgentWorkflowState) -> DoDResult:
            if len(output.steps) >= 2:
                return DoDResult(is_met=True, score=1.0)
            return DoDResult(is_met=False, feedback=["Need at least 2 steps"])

        node = CognitiveNode(
            name="planner_node",
            system_prompt="You are a planner.",
            llm_invoker=mock_invoker,
            output_schema=PlanOutput,
            dod_evaluator=dod_eval,
            max_self_retries=2,
        )

        initial_state: AgentWorkflowState = {
            "messages": [WorkflowMessage(role="user", content="Plan this")],
        }

        delta = await node(initial_state)

        # Verified that it self-corrected and passed on attempt 2
        self.assertEqual(delta["dod_evaluation"]["status"], "PASSED")
        self.assertEqual(delta["dod_evaluation"]["attempts"], 2)
        self.assertEqual(mock_invoker.invocation_count, 2)

    async def test_tool_node_success(self):
        def sample_api_call(account_id: str):
            return {"balance": 1500, "status": "active"}

        tool_node = ToolExecutionNode(
            name="fetch_balance_api",
            tool_func=sample_api_call,
        )

        state: AgentWorkflowState = {
            "pending_tool_call": {
                "name": "fetch_balance_api",
                "arguments": {"account_id": "ACC-123"},
                "idempotency_key": "IDEM-999",
            }
        }

        delta = await tool_node(state)

        result = delta["latest_tool_result"]
        self.assertEqual(result.status, ExecutionStatus.SUCCESS)
        self.assertEqual(result.output, {"balance": 1500, "status": "active"})
        self.assertEqual(result.idempotency_key, "IDEM-999")
        self.assertIsNone(delta["pending_tool_call"])

    async def test_tool_node_error_isolation(self):
        def failing_api():
            raise ConnectionError("Upstream 503 Service Unavailable")

        tool_node = ToolExecutionNode(
            name="failing_api",
            tool_func=failing_api,
        )

        state: AgentWorkflowState = {
            "pending_tool_call": {
                "name": "failing_api",
                "arguments": {},
            }
        }

        # Node should catch the error and return a FAILED ToolResult without throwing
        delta = await tool_node(state)
        result = delta["latest_tool_result"]

        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIn("Upstream 503", result.error_message)


if __name__ == "__main__":
    unittest.main()
