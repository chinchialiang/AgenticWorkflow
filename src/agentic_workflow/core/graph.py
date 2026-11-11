"""Workflow Graph Builder and Topology Assembler."""

import logging
from typing import Any, Callable, Dict, Optional

from agentic_workflow.domain.state import AgentWorkflowState
from agentic_workflow.nodes.base import GraphNode

logger = logging.getLogger(__name__)


class WorkflowGraphBuilder:
    """Builder for assembling the state machine topology.
    Can export to LangGraph StateGraph or run via internal executor.
    """

    def __init__(self):
        self.nodes: Dict[str, GraphNode[AgentWorkflowState]] = {}
        self.entry_point: Optional[str] = None
        self.edges: list[tuple[str, str]] = []
        self.conditional_edges: list[tuple[str, Callable[[AgentWorkflowState], str], dict[str, str]]] = []

    def add_node(self, node: GraphNode[AgentWorkflowState]) -> "WorkflowGraphBuilder":
        """Registers a typed node."""
        self.nodes[node.name] = node
        return self

    def set_entry_point(self, node_name: str) -> "WorkflowGraphBuilder":
        """Sets the starting node."""
        if node_name not in self.nodes:
            raise ValueError(f"Node '{node_name}' not registered.")
        self.entry_point = node_name
        return self

    def add_edge(self, from_node: str, to_node: str) -> "WorkflowGraphBuilder":
        """Adds a direct transition edge."""
        self.edges.append((from_node, to_node))
        return self

    def add_conditional_edges(
        self,
        from_node: str,
        router_func: Callable[[AgentWorkflowState], str],
        route_map: dict[str, str],
    ) -> "WorkflowGraphBuilder":
        """Adds content-based conditional routing."""
        self.conditional_edges.append((from_node, router_func, route_map))
        return self

    def compile_langgraph(self, checkpointer: Optional[Any] = None) -> Any:
        """Compiles this definition into a native LangGraph StateGraph if langgraph is installed."""
        try:
            from langgraph.graph import StateGraph, END  # type: ignore
        except ImportError as e:
            raise ImportError(
                "LangGraph is not installed. Run `pip install langgraph` to compile native LangGraph graphs."
            ) from e

        graph = StateGraph(AgentWorkflowState)

        # Register nodes
        for name, node in self.nodes.items():
            graph.add_node(name, node)

        # Entry point
        if self.entry_point:
            graph.set_entry_point(self.entry_point)

        # Normal edges
        for from_n, to_n in self.edges:
            target = END if to_n == "END" else to_n
            graph.add_edge(from_n, target)

        # Conditional edges
        for from_n, router, route_map in self.conditional_edges:
            mapped_routes = {k: (END if v == "END" else v) for k, v in route_map.items()}
            graph.add_conditional_edges(from_n, router, mapped_routes)

        return graph.compile(checkpointer=checkpointer)
