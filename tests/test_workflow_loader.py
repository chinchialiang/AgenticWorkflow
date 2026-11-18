"""Unit tests for WorkflowDefinition Graph IR and WorkflowLoader."""

import unittest
from pydantic import ValidationError

from agentic_workflow.core import WorkflowLoader
from agentic_workflow.domain import (
    ConditionalEdgeSpec,
    DoDContract,
    EdgeSpec,
    EvalConfig,
    EvaluatorSpec,
    LLMNodeConfig,
    WorkflowDefinition,
)
from agentic_workflow.gateway.event_broker import InMemoryAsyncEventBroker
from agentic_workflow.gateway.llm import MockLLMInvoker
from agentic_workflow.nodes import BaseLLMNode


class TestWorkflowLoader(unittest.IsolatedAsyncioTestCase):
    def test_topology_validation_rejects_invalid_references(self):
        node_a = LLMNodeConfig(name="node_a", system_prompt="A")

        with self.assertRaises(ValidationError):
            WorkflowDefinition(
                workflow_id="wf-1",
                entry_point="missing_node",
                nodes=[node_a],
            )

        with self.assertRaises(ValidationError):
            WorkflowDefinition(
                workflow_id="wf-2",
                entry_point="node_a",
                nodes=[node_a],
                edges=[EdgeSpec(source="node_a", target="nonexistent")],
            )

        with self.assertRaises(ValidationError):
            WorkflowDefinition(
                workflow_id="wf-3",
                entry_point="node_a",
                nodes=[node_a, node_a],
            )

    async def test_load_from_json_and_execute_with_conditional_router(self):
        definition = WorkflowDefinition(
            workflow_id="support-flow",
            version="1.0.0",
            tenant_id="tenant-acme",
            entry_point="drafter",
            nodes=[
                LLMNodeConfig(
                    name="drafter",
                    system_prompt="Draft a JSON reply.",
                    user_prompt_template="Ticket: {{ state.artifacts.ticket }}",
                    dod=DoDContract(output_json_schema={"type": "object", "required": ["reply"]}),
                    eval=EvalConfig(evaluators=[EvaluatorSpec(name="schema", kind="schema")]),
                    output_artifact_key="draft",
                ),
                LLMNodeConfig(
                    name="escalation",
                    system_prompt="Summarize escalation reason.",
                ),
            ],
            conditional_edges=[
                ConditionalEdgeSpec(
                    source="drafter",
                    condition_type="dod_status",
                    route_map={"PASSED": "END", "FAILED": "escalation"},
                )
            ],
            ui_metadata={"nodes": {"drafter": {"x": 100, "y": 100}}},
        )

        broker = InMemoryAsyncEventBroker()
        invoker = MockLLMInvoker(canned_response='{"reply": "We have shipped your order."}')
        loader = WorkflowLoader(llm_invoker=invoker, event_broker=broker)

        builder = loader.load(definition.model_dump_json())

        self.assertEqual(builder.entry_point, "drafter")
        self.assertIsInstance(builder.nodes["drafter"], BaseLLMNode)
        self.assertIs(builder.nodes["drafter"].event_broker, broker)
        self.assertEqual(len(builder.conditional_edges), 1)

        # Execute hydrated node and evaluate compiled conditional router
        delta = await builder.nodes["drafter"]({"artifacts": {"ticket": "Where is my order?"}})
        self.assertEqual(delta["dod_evaluation"]["status"], "PASSED")

        _, router_fn, route_map = builder.conditional_edges[0]
        next_target = route_map[router_fn(delta)]
        self.assertEqual(next_target, "END")

    async def test_load_with_per_node_invoker_factory(self):
        definition = WorkflowDefinition(
            workflow_id="multi-model-flow",
            entry_point="fast_node",
            nodes=[
                LLMNodeConfig(name="fast_node", system_prompt="Fast"),
                LLMNodeConfig(name="smart_node", system_prompt="Smart"),
            ],
            edges=[EdgeSpec(source="fast_node", target="smart_node"), EdgeSpec(source="smart_node", target="END")],
        )

        invokers = {
            "fast_node": MockLLMInvoker(canned_response="fast-ok"),
            "smart_node": MockLLMInvoker(canned_response="smart-ok"),
        }

        loader = WorkflowLoader(llm_invoker=lambda cfg: invokers[cfg.name])
        builder = loader.load(definition)

        res1 = await builder.nodes["fast_node"]({"messages": []})
        res2 = await builder.nodes["smart_node"]({"messages": []})
        self.assertEqual(res1["messages"].content, "fast-ok")
        self.assertEqual(res2["messages"].content, "smart-ok")
