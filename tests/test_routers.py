"""Unit tests for content-based routers and circuit breakers."""

import unittest
from agentic_workflow.domain.models import ExecutionStatus
from agentic_workflow.domain.state import AgentWorkflowState
from agentic_workflow.core.routers import evaluate_transition


class TestRouters(unittest.TestCase):
    def test_circuit_breaker_max_steps(self):
        state: AgentWorkflowState = {
            "step_count": 25,
            "max_steps": 25,
        }
        route = evaluate_transition(state)
        self.assertEqual(route, "error_handler")

    def test_human_approval_route(self):
        state: AgentWorkflowState = {
            "step_count": 2,
            "max_steps": 25,
            "requires_approval": True,
        }
        route = evaluate_transition(state)
        self.assertEqual(route, "human_approval")

    def test_tool_execution_route(self):
        state: AgentWorkflowState = {
            "step_count": 2,
            "max_steps": 25,
            "requires_approval": False,
            "pending_tool_call": {"name": "test_tool", "arguments": {}},
        }
        route = evaluate_transition(state)
        self.assertEqual(route, "tool_execution")

    def test_completed_route(self):
        state: AgentWorkflowState = {
            "step_count": 5,
            "max_steps": 25,
            "execution_status": ExecutionStatus.COMPLETED,
        }
        route = evaluate_transition(state)
        self.assertEqual(route, "end")


if __name__ == "__main__":
    unittest.main()
