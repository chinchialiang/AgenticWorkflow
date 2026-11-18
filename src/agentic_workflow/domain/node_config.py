"""Declarative configuration contracts for LLM nodes, skills, DoD, Eval, and governance."""

from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class RiskLevel(str, Enum):
    """Risk classification for skills and tools."""
    READ_ONLY = "read_only"
    WRITE = "write"
    CRITICAL = "critical"


class ContextPolicy(str, Enum):
    """Controls how prior conversation messages are injected into an LLM node."""
    NONE = "none"
    LAST_N = "last_n"
    FULL = "full"


class FailurePolicy(str, Enum):
    """Action taken when an LLM node exhausts retries without meeting DoD."""
    FAIL_WORKFLOW = "fail_workflow"
    FALLBACK_NODE = "fallback_node"
    WAITING_APPROVAL = "waiting_approval"


class ModelConfig(BaseModel):
    """LLM provider and inference hyperparameters."""
    provider: str = Field(default="openai", description="Model provider identifier.")
    model_id: str = Field(default="gpt-4o-mini", description="Target model name.")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, gt=0)


class SkillSpec(BaseModel):
    """Structured skill binding domain instructions, scoped tools, and security metadata."""
    skill_id: str = Field(..., min_length=1)
    description: str = Field(default="")
    instructions: str = Field(default="", description="Domain rules injected when skill is active.")
    tool_refs: list[str] = Field(default_factory=list, description="Whitelisted tool or MCP identifiers.")
    risk_level: RiskLevel = Field(default=RiskLevel.READ_ONLY)
    requires_approval: bool = Field(default=False, description="Force HITL approval before side-effect execution.")
    secret_refs: list[str] = Field(
        default_factory=list,
        description="Secret Manager / KMS reference URIs (e.g. vault://crm/api_key). Raw secrets are forbidden.",
    )

    @field_validator("secret_refs")
    @classmethod
    def validate_secret_refs_are_uris(cls, refs: list[str]) -> list[str]:
        """Ensure secret_refs only store reference URIs, never raw credentials."""
        allowed_prefixes = ("vault://", "env://", "kms://", "secret://")
        for ref in refs:
            if not ref.startswith(allowed_prefixes):
                raise ValueError(
                    f"Invalid secret_ref '{ref}'. Must be a reference URI starting with one of {allowed_prefixes}."
                )
        return refs


class DoDContract(BaseModel):
    """Formal Definition of Done combining structural schema and semantic criteria."""
    output_json_schema: Optional[dict[str, Any]] = Field(
        default=None,
        description="JSON Schema contract that the node output must satisfy.",
    )
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="Natural-language acceptance criteria verified by semantic evaluators.",
    )


EvaluatorKind = Literal["schema", "regex", "length", "forbidden_terms", "llm_judge"]


class EvaluatorSpec(BaseModel):
    """Declarative specification for a single evaluation step."""
    name: str = Field(..., min_length=1)
    kind: EvaluatorKind
    params: dict[str, Any] = Field(default_factory=dict)


class EvalConfig(BaseModel):
    """Evaluation pipeline and self-correction retry configuration."""
    evaluators: list[EvaluatorSpec] = Field(default_factory=list)
    pass_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    max_self_retries: int = Field(default=2, ge=0, le=10)
    on_failure: FailurePolicy = Field(default=FailurePolicy.FAIL_WORKFLOW)
    fallback_node: Optional[str] = Field(default=None)


class GuardrailConfig(BaseModel):
    """Pre-LLM and Post-LLM security guardrail settings."""
    enable_pii_redaction: bool = Field(default=True)
    enable_injection_check: bool = Field(default=True)
    blocked_patterns: list[str] = Field(default_factory=list)


class BudgetPolicy(BaseModel):
    """FinOps resource and timeout guardrails per node execution."""
    max_tokens: Optional[int] = Field(default=None, gt=0)
    max_cost_usd: Optional[float] = Field(default=None, gt=0.0)
    timeout_seconds: float = Field(default=60.0, gt=0.0)


class LLMNodeConfig(BaseModel):
    """Serializable, UI-ready contract for a cognitive LLM workflow node."""
    name: str = Field(..., min_length=1)
    llm: ModelConfig = Field(default_factory=ModelConfig)
    system_prompt: str = Field(..., min_length=1)
    user_prompt_template: str = Field(
        default="",
        description="Task-specific prompt template supporting safe {{ state.artifacts.xxx }} interpolation.",
    )
    context_policy: ContextPolicy = Field(default=ContextPolicy.LAST_N)
    context_last_n: int = Field(default=5, ge=0, le=100)
    skills: list[SkillSpec] = Field(default_factory=list)
    dod: DoDContract = Field(default_factory=DoDContract)
    eval: EvalConfig = Field(default_factory=EvalConfig)
    guardrails: GuardrailConfig = Field(default_factory=GuardrailConfig)
    budget_policy: BudgetPolicy = Field(default_factory=BudgetPolicy)
    output_artifact_key: Optional[str] = Field(
        default=None,
        description="If set, stores the validated node output under state['artifacts'][output_artifact_key].",
    )
