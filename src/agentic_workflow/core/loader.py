"""WorkflowLoader: compiles declarative WorkflowDefinition (Graph IR) into WorkflowGraphBuilder."""

import inspect
from typing import Any, Callable, Optional, Union

from pydantic import BaseModel

from agentic_workflow.core.events import EventBroker
from agentic_workflow.core.graph import WorkflowGraphBuilder
from agentic_workflow.domain.models import ExecutionStatus
from agentic_workflow.domain.node_config import LLMNodeConfig
from agentic_workflow.domain.state import AgentWorkflowState
from agentic_workflow.domain.workflow_config import ConditionalEdgeSpec, WorkflowDefinition
from agentic_workflow.nodes.llm_node import BaseLLMNode

InvokerFactory = Union[Callable[..., Any], Callable[[LLMNodeConfig], Callable[..., Any]]]


def _is_node_factory(candidate: Any) -> bool:
    """Distinguishes a (LLMNodeConfig) -> Invoker factory from a direct invoker callable."""
    if not callable(candidate):
        return False
    try:
        sig = inspect.signature(candidate)
    except (TypeError, ValueError):
        return False
    params = [
        p for p in sig.parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    return len(params) == 1


def build_conditional_router(spec: ConditionalEdgeSpec) -> Callable[[AgentWorkflowState], str]:
    """Creates a state-inspecting router function from a declarative ConditionalEdgeSpec."""
    fallback_key = next(iter(spec.route_map.keys()))

    def _router(state: AgentWorkflowState) -> str:
        if spec.condition_type == "dod_status":
            dod = state.get("dod_evaluation") or {}
            outcome = str(dod.get("status", "FAILED"))
            return outcome if outcome in spec.route_map else fallback_key

        if spec.condition_type == "execution_status":
            status = state.get("execution_status", ExecutionStatus.RUNNING)
            outcome = status.value if isinstance(status, ExecutionStatus) else str(status)
            return outcome if outcome in spec.route_map else fallback_key

        if spec.condition_type == "eval_score_threshold":
            dod = state.get("dod_evaluation") or {}
            score = float(dod.get("score", 0.0))
            threshold = spec.threshold if spec.threshold is not None else 0.8
            outcome = "PASS" if score >= threshold else "FAIL"
            return outcome if outcome in spec.route_map else fallback_key

        return fallback_key

    return _router


class WorkflowLoader:
    """Hydrates a declarative WorkflowDefinition (JSON/dict/model) into an executable WorkflowGraphBuilder."""

    def __init__(
        self,
        llm_invoker: InvokerFactory,
        judge_invoker: Optional[Callable[..., Any]] = None,
        output_models: Optional[dict[str, type[BaseModel]]] = None,
        event_broker: Optional[EventBroker] = None,
    ):
        self.llm_invoker = llm_invoker
        self.judge_invoker = judge_invoker
        self.output_models = output_models or {}
        self.event_broker = event_broker

    @staticmethod
    def parse_definition(source: Union[WorkflowDefinition, dict[str, Any], str]) -> WorkflowDefinition:
        """Parses a JSON string, dictionary, or WorkflowDefinition into a validated Graph IR."""
        if isinstance(source, WorkflowDefinition):
            return source
        if isinstance(source, str):
            return WorkflowDefinition.model_validate_json(source)
        if isinstance(source, dict):
            return WorkflowDefinition.model_validate(source)
        raise TypeError(f"Unsupported workflow definition type: {type(source)}")

    def load(
        self,
        source: Union[WorkflowDefinition, dict[str, Any], str],
    ) -> WorkflowGraphBuilder:
        """Compiles a declarative workflow definition into a configured WorkflowGraphBuilder."""
        definition = self.parse_definition(source)
        builder = WorkflowGraphBuilder(event_broker=self.event_broker)

        use_factory = _is_node_factory(self.llm_invoker)
        for node_cfg in definition.nodes:
            invoker = self.llm_invoker(node_cfg) if use_factory else self.llm_invoker
            node = BaseLLMNode(
                config=node_cfg,
                llm_invoker=invoker,
                output_model=self.output_models.get(node_cfg.name),
                judge_invoker=self.judge_invoker,
                event_broker=self.event_broker,
            )
            builder.add_node(node)

        builder.set_entry_point(definition.entry_point)

        for edge in definition.edges:
            builder.add_edge(edge.source, edge.target)

        for cond in definition.conditional_edges:
            router_fn = build_conditional_router(cond)
            builder.add_conditional_edges(cond.source, router_fn, cond.route_map)

        return builder
