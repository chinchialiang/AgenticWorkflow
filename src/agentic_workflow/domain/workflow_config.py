"""Declarative Workflow Graph IR schema for serialization, DB storage, and UI round-trip."""

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, model_validator

from agentic_workflow.domain.node_config import LLMNodeConfig


class EdgeSpec(BaseModel):
    """Direct transition edge between two workflow nodes (or END)."""
    source: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)


ConditionalType = Literal["dod_status", "execution_status", "eval_score_threshold"]


class ConditionalEdgeSpec(BaseModel):
    """Declarative conditional routing rule evaluated after a node completes."""
    source: str = Field(..., min_length=1)
    condition_type: ConditionalType = Field(default="dod_status")
    route_map: dict[str, str] = Field(
        ...,
        min_length=1,
        description="Maps condition outcomes (e.g. 'PASSED', 'FAILED') to target node names or 'END'.",
    )
    threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Score threshold used when condition_type == 'eval_score_threshold'.",
    )


class WorkflowDefinition(BaseModel):
    """Serializable Graph IR bridging React Flow UI, DB persistence, and WorkflowGraphBuilder."""
    workflow_id: str = Field(..., min_length=1)
    version: str = Field(default="1.0.0", min_length=1)
    tenant_id: str = Field(default="default", min_length=1)
    name: str = Field(default="")
    description: str = Field(default="")
    entry_point: str = Field(..., min_length=1)
    max_steps: int = Field(default=25, ge=1, le=200)
    max_budget_usd: Optional[float] = Field(default=None, gt=0.0)
    nodes: list[LLMNodeConfig] = Field(..., min_length=1)
    edges: list[EdgeSpec] = Field(default_factory=list)
    conditional_edges: list[ConditionalEdgeSpec] = Field(default_factory=list)
    ui_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Canvas layout metadata (node coordinates, viewport) for visual builder.",
    )

    @model_validator(mode="after")
    def validate_topology(self) -> "WorkflowDefinition":
        """Ensures unique node names, valid entry_point, and valid edge references."""
        node_names = [node.name for node in self.nodes]
        if len(node_names) != len(set(node_names)):
            raise ValueError("Duplicate node names found in WorkflowDefinition.")

        valid_nodes = set(node_names)
        if self.entry_point not in valid_nodes:
            raise ValueError(f"Entry point '{self.entry_point}' is not defined in nodes.")

        valid_targets = valid_nodes | {"END"}
        for edge in self.edges:
            if edge.source not in valid_nodes:
                raise ValueError(f"Edge source '{edge.source}' does not exist in nodes.")
            if edge.target not in valid_targets:
                raise ValueError(f"Edge target '{edge.target}' does not exist in nodes or 'END'.")

        for cond in self.conditional_edges:
            if cond.source not in valid_nodes:
                raise ValueError(f"Conditional edge source '{cond.source}' does not exist in nodes.")
            for outcome, target in cond.route_map.items():
                if target not in valid_targets:
                    raise ValueError(
                        f"Conditional route '{outcome}' -> '{target}' references unknown target."
                    )

        return self
