"""BaseLLMNode implementation driven by declarative LLMNodeConfig contracts."""

import asyncio
import inspect
import json
import logging
import re
from typing import Any, Callable, Optional, Type

from pydantic import BaseModel, ValidationError

from agentic_workflow.core.events import EventBroker
from agentic_workflow.domain.models import (
    DoDResult,
    ExecutionStatus,
    LLMResponse,
    LLMUsage,
    NodeStatus,
    WorkflowMessage,
)
from agentic_workflow.domain.node_config import (
    ContextPolicy,
    EvaluatorSpec,
    FailurePolicy,
    LLMNodeConfig,
)
from agentic_workflow.domain.state import AgentWorkflowState
from agentic_workflow.gateway.llm import normalize_llm_response
from agentic_workflow.nodes.base import GraphNode

logger = logging.getLogger("agentic_workflow.nodes.llm")

_TEMPLATE_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SECRET_KEY_PATTERN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{16,})\b")
_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"reveal\s+(?:your\s+)?system\s+prompt", re.IGNORECASE),
)


def render_safe_template(template: str, state: AgentWorkflowState) -> str:
    """Renders {{ state.xxx }} placeholders via a strict dot-path lookup.

    Avoids eval/full template engines to prevent Server-Side Template Injection (SSTI).
    Any path containing dunder segments ('__') is rejected.
    """
    if not template:
        return ""

    context: dict[str, Any] = {
        "state": {
            "artifacts": dict(state.get("artifacts") or {}),
            "thread_id": state.get("thread_id", "default"),
            "tenant_id": state.get("tenant_id", ""),
            "trace_id": state.get("trace_id", ""),
            "current_node": state.get("current_node", ""),
        }
    }

    def _replace(match: re.Match[str]) -> str:
        path = match.group(1)
        parts = path.split(".")
        if any(part.startswith("__") for part in parts):
            return "[BLOCKED_TEMPLATE_EXPRESSION]"
        current: Any = context
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return ""
        if isinstance(current, (dict, list)):
            return json.dumps(current, ensure_ascii=False)
        return str(current)

    return _TEMPLATE_VAR_PATTERN.sub(_replace, template)


def redact_sensitive_text(text: str) -> str:
    """Masks common PII (emails) and API secret patterns before external LLM calls or logging."""
    if not text:
        return text
    masked = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    masked = _SECRET_KEY_PATTERN.sub("[REDACTED_SECRET]", masked)
    return masked


def detect_prompt_injection(text: str, extra_patterns: list[str]) -> Optional[str]:
    """Returns the matched violation description if injection or blocked pattern is detected."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return f"Prompt injection pattern detected: '{pattern.pattern}'"
    for raw in extra_patterns:
        if raw and re.search(raw, text, re.IGNORECASE):
            return f"Blocked pattern detected: '{raw}'"
    return None


class BaseLLMNode(GraphNode[AgentWorkflowState]):
    """Declarative, governance-ready LLM node executing a 5-pillar contract:
    1. System Prompt (role & invariants)
    2. User Prompt (task template with safe state interpolation & context policy)
    3. Skills (scoped instructions, whitelisted tool_refs, risk metadata)
    4. Definition of Done (JSON Schema / Pydantic + acceptance criteria)
    5. Eval Pipeline (deterministic + semantic evaluators with self-correction & budget guardrails)
    """

    def __init__(
        self,
        config: LLMNodeConfig,
        llm_invoker: Callable[..., Any],
        output_model: Optional[Type[BaseModel]] = None,
        judge_invoker: Optional[Callable[..., Any]] = None,
        event_broker: Optional[EventBroker] = None,
    ):
        super().__init__(name=config.name, event_broker=event_broker)
        self.config = config
        self.llm_invoker = llm_invoker
        self.output_model = output_model
        self.judge_invoker = judge_invoker

    async def _on_execute(self, state: AgentWorkflowState) -> dict[str, Any]:
        # 1. Build scoped messages (Task User Prompt + Context Policy)
        messages, injection_error = self._prepare_messages(state)
        if injection_error:
            return self._build_failure_delta(
                reason=injection_error,
                usage=LLMUsage(model_id=self.config.llm.model_id),
                attempts=0,
                feedback=[injection_error],
            )

        # 2. Compile System Prompt with active Skill instructions
        base_system_prompt = self._compile_system_prompt()
        allowed_tools = self._collect_allowed_tools()

        cumulative_tokens = 0
        cumulative_cost = 0.0
        feedback_notes: list[str] = []
        max_attempts = self.config.eval.max_self_retries + 1

        for attempt in range(1, max_attempts + 1):
            if feedback_notes:
                await self._transition_to(
                    NodeStatus.RETRYING,
                    attempt=attempt,
                    max_retries=self.config.eval.max_self_retries,
                    reasons=feedback_notes,
                    message=f"Node '{self.name}' retrying with evaluation feedback.",
                )

            prompt_for_attempt = base_system_prompt
            if feedback_notes:
                prompt_for_attempt += (
                    "\n\n[Evaluation Feedback from Previous Attempt]:\n"
                    + "\n".join(f"- {note}" for note in feedback_notes)
                )

            # 3. Invoke LLM with timeout guardrail
            raw_res = await self._invoke_with_timeout(prompt_for_attempt, messages, allowed_tools)
            llm_response = normalize_llm_response(raw_res, default_model_id=self.config.llm.model_id)

            # 4. FinOps: Accumulate usage & enforce BudgetPolicy
            cumulative_tokens += llm_response.usage.total_tokens
            cumulative_cost += llm_response.usage.cost_usd
            budget_error = self._check_budget(cumulative_tokens, cumulative_cost)
            if budget_error:
                return self._build_failure_delta(
                    reason=budget_error,
                    usage=self._aggregate_usage(cumulative_tokens, cumulative_cost),
                    attempts=attempt,
                    feedback=[budget_error],
                )

            # 5. Post-LLM Guardrail (PII redaction before evaluation, logging, or state persistence)
            safe_content = self._sanitize_output(llm_response.content)

            # 6. Dual-Stage Eval Pipeline
            await self._transition_to(
                NodeStatus.EVALUATING,
                stage="eval_pipeline",
                attempt=attempt,
                trace_id=state.get("trace_id"),
            )
            eval_result = await self._run_eval_pipeline(safe_content, state)
            if not eval_result.is_met:
                feedback_notes = list(eval_result.feedback)
                continue

            # 7. Success: Check if any critical skill requires HITL approval before exiting
            return self._build_success_delta(
                content=safe_content,
                eval_result=eval_result,
                attempts=attempt,
                usage=self._aggregate_usage(cumulative_tokens, cumulative_cost),
            )

        # Exhausted all retry attempts
        return self._build_failure_delta(
            reason=f"Node '{self.name}' failed to meet DoD after {max_attempts} attempts.",
            usage=self._aggregate_usage(cumulative_tokens, cumulative_cost),
            attempts=max_attempts,
            feedback=feedback_notes,
        )

    def _prepare_messages(self, state: AgentWorkflowState) -> tuple[list[WorkflowMessage], Optional[str]]:
        """Applies ContextPolicy, renders User Prompt template, and runs Pre-LLM guardrails."""
        history = list(state.get("messages") or [])
        policy = self.config.context_policy
        if policy == ContextPolicy.NONE:
            selected_history: list[WorkflowMessage] = []
        elif policy == ContextPolicy.LAST_N:
            selected_history = history[-self.config.context_last_n :] if self.config.context_last_n > 0 else []
        else:
            selected_history = history

        rendered_task = render_safe_template(self.config.user_prompt_template, state)
        if rendered_task:
            selected_history.append(WorkflowMessage(role="user", content=rendered_task, name=f"{self.name}_task"))

        sanitized: list[WorkflowMessage] = []
        for msg in selected_history:
            text = msg.content
            if self.config.guardrails.enable_injection_check:
                violation = detect_prompt_injection(text, self.config.guardrails.blocked_patterns)
                if violation:
                    return [], violation
            if self.config.guardrails.enable_pii_redaction:
                text = redact_sensitive_text(text)
            sanitized.append(
                WorkflowMessage(role=msg.role, content=text, name=msg.name, metadata=msg.metadata)
            )
        return sanitized, None

    def _compile_system_prompt(self) -> str:
        """Combines base System Prompt with active Skill instructions."""
        parts = [self.config.system_prompt]
        skill_blocks = [
            f"- [{skill.skill_id}] {skill.instructions}".strip()
            for skill in self.config.skills
            if skill.instructions
        ]
        if skill_blocks:
            parts.append("\n[Active Skills & Instructions]:\n" + "\n".join(skill_blocks))
        if self.config.dod.acceptance_criteria:
            criteria_text = "\n".join(f"- {c}" for c in self.config.dod.acceptance_criteria)
            parts.append(f"\n[Definition of Done Criteria]:\n{criteria_text}")
        return "\n".join(parts)

    def _collect_allowed_tools(self) -> list[str]:
        """Collects deduplicated tool_refs from configured skills (Least Privilege)."""
        seen: set[str] = set()
        tools: list[str] = []
        for skill in self.config.skills:
            for ref in skill.tool_refs:
                if ref not in seen:
                    seen.add(ref)
                    tools.append(ref)
        return tools

    async def _invoke_with_timeout(
        self,
        system_prompt: str,
        messages: list[WorkflowMessage],
        tools: list[str],
    ) -> Any:
        coro_or_val = self.llm_invoker(system_prompt, messages, tools)
        if inspect.isawaitable(coro_or_val):
            return await asyncio.wait_for(coro_or_val, timeout=self.config.budget_policy.timeout_seconds)
        return coro_or_val

    def _check_budget(self, total_tokens: int, total_cost: float) -> Optional[str]:
        budget = self.config.budget_policy
        if budget.max_tokens is not None and total_tokens > budget.max_tokens:
            return f"Budget exceeded: total_tokens ({total_tokens}) > max_tokens ({budget.max_tokens})."
        if budget.max_cost_usd is not None and total_cost > budget.max_cost_usd:
            return f"Budget exceeded: cost_usd ({total_cost:.4f}) > max_cost_usd ({budget.max_cost_usd:.4f})."
        return None

    def _sanitize_output(self, content: Any) -> Any:
        if not self.config.guardrails.enable_pii_redaction:
            return content
        if isinstance(content, str):
            return redact_sensitive_text(content)
        return content

    async def _run_eval_pipeline(self, output: Any, state: AgentWorkflowState) -> DoDResult:
        """Runs deterministic evaluators first, followed by semantic/LLM-judge evaluators."""
        evaluators = list(self.config.eval.evaluators)

        # Implicit schema check if output_model or output_json_schema is configured without explicit 'schema' spec
        has_explicit_schema = any(e.kind == "schema" for e in evaluators)
        if not has_explicit_schema and (self.output_model or self.config.dod.output_json_schema):
            evaluators.insert(0, EvaluatorSpec(name="implicit_schema", kind="schema"))

        if not evaluators:
            return DoDResult(is_met=True, score=1.0)

        feedback: list[str] = []
        scores: list[float] = []

        for spec in evaluators:
            res = await self._run_single_evaluator(spec, output, state)
            scores.append(res.score)
            if not res.is_met:
                feedback.extend(res.feedback or [f"Evaluator '{spec.name}' failed."])

        avg_score = round(sum(scores) / len(scores), 4) if scores else 1.0
        is_met = (len(feedback) == 0) and (avg_score >= self.config.eval.pass_threshold)
        if not is_met and not feedback:
            feedback.append(
                f"Average eval score {avg_score} is below pass_threshold {self.config.eval.pass_threshold}."
            )
        return DoDResult(is_met=is_met, score=avg_score, feedback=feedback)

    async def _run_single_evaluator(
        self,
        spec: EvaluatorSpec,
        output: Any,
        state: AgentWorkflowState,
    ) -> DoDResult:
        text = output.model_dump_json() if isinstance(output, BaseModel) else (
            json.dumps(output, ensure_ascii=False) if isinstance(output, dict) else str(output)
        )

        if spec.kind == "schema":
            return self._eval_schema(output)
        if spec.kind == "regex":
            pattern = spec.params.get("pattern", "")
            if pattern and not re.search(pattern, text):
                return DoDResult(is_met=False, score=0.0, feedback=[f"Output did not match regex '{pattern}'."])
            return DoDResult(is_met=True, score=1.0)
        if spec.kind == "length":
            min_len = spec.params.get("min_length", 0)
            max_len = spec.params.get("max_length")
            if len(text) < min_len:
                return DoDResult(is_met=False, score=0.0, feedback=[f"Output length {len(text)} < min_length {min_len}."])
            if max_len is not None and len(text) > max_len:
                return DoDResult(is_met=False, score=0.0, feedback=[f"Output length {len(text)} > max_length {max_len}."])
            return DoDResult(is_met=True, score=1.0)
        if spec.kind == "forbidden_terms":
            terms = spec.params.get("terms", [])
            found = [t for t in terms if t.lower() in text.lower()]
            if found:
                return DoDResult(is_met=False, score=0.0, feedback=[f"Forbidden terms found: {found}."])
            return DoDResult(is_met=True, score=1.0)
        if spec.kind == "llm_judge":
            return await self._eval_llm_judge(text, state)

        return DoDResult(is_met=False, score=0.0, feedback=[f"Unknown evaluator kind: {spec.kind}"])

    def _eval_schema(self, output: Any) -> DoDResult:
        if self.output_model is not None:
            try:
                if isinstance(output, self.output_model):
                    return DoDResult(is_met=True, score=1.0)
                if isinstance(output, dict):
                    self.output_model.model_validate(output)
                    return DoDResult(is_met=True, score=1.0)
                if isinstance(output, str):
                    self.output_model.model_validate_json(output)
                    return DoDResult(is_met=True, score=1.0)
                return DoDResult(is_met=False, score=0.0, feedback=[f"Unsupported output type: {type(output)}"])
            except ValidationError as exc:
                return DoDResult(is_met=False, score=0.0, feedback=[f"Schema Validation Error: {exc}"])

        schema = self.config.dod.output_json_schema
        if not schema:
            return DoDResult(is_met=True, score=1.0)

        try:
            parsed = output if isinstance(output, dict) else json.loads(str(output))
        except (json.JSONDecodeError, TypeError) as exc:
            return DoDResult(is_met=False, score=0.0, feedback=[f"Invalid JSON output: {exc}"])

        if not isinstance(parsed, dict):
            return DoDResult(is_met=False, score=0.0, feedback=["Expected JSON object output."])

        required = schema.get("required", [])
        missing = [field for field in required if field not in parsed]
        if missing:
            return DoDResult(is_met=False, score=0.0, feedback=[f"Missing required schema fields: {missing}"])
        return DoDResult(is_met=True, score=1.0)

    async def _eval_llm_judge(self, output_text: str, state: AgentWorkflowState) -> DoDResult:
        if self.judge_invoker is None:
            return DoDResult(is_met=True, score=1.0)
        res = self.judge_invoker(output_text, self.config.dod.acceptance_criteria, state)
        if inspect.isawaitable(res):
            res = await res
        if isinstance(res, DoDResult):
            return res
        if isinstance(res, dict):
            return DoDResult.model_validate(res)
        return DoDResult(is_met=False, score=0.0, feedback=["Invalid response from judge_invoker."])

    def _aggregate_usage(self, total_tokens: int, total_cost: float) -> LLMUsage:
        return LLMUsage(
            total_tokens=total_tokens,
            cost_usd=round(total_cost, 6),
            model_id=self.config.llm.model_id,
        )

    def _build_success_delta(
        self,
        content: Any,
        eval_result: DoDResult,
        attempts: int,
        usage: LLMUsage,
    ) -> dict[str, Any]:
        serialized = (
            content.model_dump_json()
            if isinstance(content, BaseModel)
            else (json.dumps(content, ensure_ascii=False) if isinstance(content, dict) else str(content))
        )
        requires_hitl = any(skill.requires_approval for skill in self.config.skills)
        next_status = ExecutionStatus.WAITING_APPROVAL if requires_hitl else ExecutionStatus.RUNNING

        delta: dict[str, Any] = {
            "messages": WorkflowMessage(
                role="assistant",
                content=serialized,
                name=self.name,
                metadata={"usage": usage.model_dump()},
            ),
            "dod_evaluation": {
                "status": "PASSED",
                "score": eval_result.score,
                "attempts": attempts,
                "usage": usage.model_dump(),
            },
            "execution_status": next_status,
            "requires_approval": requires_hitl,
            "step_count": 1,
        }
        if self.config.output_artifact_key:
            delta["artifacts"] = {self.config.output_artifact_key: content}
        return delta

    def _build_failure_delta(
        self,
        reason: str,
        usage: LLMUsage,
        attempts: int,
        feedback: list[str],
    ) -> dict[str, Any]:
        on_failure = self.config.eval.on_failure
        if on_failure == FailurePolicy.WAITING_APPROVAL:
            exec_status = ExecutionStatus.WAITING_APPROVAL
        else:
            exec_status = ExecutionStatus.FAILED

        return {
            "execution_status": exec_status,
            "requires_approval": on_failure == FailurePolicy.WAITING_APPROVAL,
            "error_message": reason,
            "dod_evaluation": {
                "status": "FAILED",
                "attempts": attempts,
                "feedback": feedback,
                "usage": usage.model_dump(),
                "fallback_node": self.config.eval.fallback_node,
            },
            "step_count": 1,
        }
