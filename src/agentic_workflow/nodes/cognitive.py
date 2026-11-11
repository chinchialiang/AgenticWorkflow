"""Cognitive / LLM node implementation with System Prompt, Skills, DoD, and Eval."""

import logging
from typing import Any, Callable, Optional, Type
from pydantic import BaseModel, ValidationError

from agentic_workflow.domain.models import DoDResult, ExecutionStatus, NodeStatus, WorkflowMessage
from agentic_workflow.domain.state import AgentWorkflowState
from agentic_workflow.nodes.base import GraphNode

logger = logging.getLogger("agentic_workflow.nodes.cognitive")


class CognitiveNode(GraphNode[AgentWorkflowState]):
    """Stochastic LLM node governed by an enterprise contract:
    - System Prompt: Role definition and invariants
    - Skills: Scoped tool registry for this node
    - DoD (Definition of Done): Formal Pydantic schema contract
    - Eval: Dual-stage validation (deterministic schema + semantic DoD check)
    - Self-correction retry loop with lifecycle state transitions
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        llm_invoker: Callable[[str, list[WorkflowMessage], list[Any]], Any],
        skills: Optional[list[Any]] = None,
        output_schema: Optional[Type[BaseModel]] = None,
        dod_evaluator: Optional[Callable[[Any, AgentWorkflowState], DoDResult]] = None,
        max_self_retries: int = 2,
    ):
        super().__init__(name)
        self.system_prompt = system_prompt
        self.llm_invoker = llm_invoker
        self.skills = skills or []
        self.output_schema = output_schema
        self.dod_evaluator = dod_evaluator
        self.max_self_retries = max_self_retries

    async def _on_execute(self, state: AgentWorkflowState) -> dict[str, Any]:
        messages = list(state.get("messages") or [])
        feedback_notes: list[str] = []

        for attempt in range(self.max_self_retries + 1):
            # 1. Compile prompt with feedback if retrying
            augmented_prompt = self.system_prompt
            if feedback_notes:
                self._transition_to(
                    NodeStatus.RETRYING,
                    attempt=attempt + 1,
                    max_retries=self.max_self_retries,
                    reasons=feedback_notes,
                    message=f"Node '{self.name}' retrying with evaluation feedback.",
                )
                augmented_prompt += "\n\n[Evaluation Feedback from Previous Attempt]:\n" + "\n".join(feedback_notes)

            # 2. Invoke LLM
            raw_response = await self._invoke_llm(augmented_prompt, messages)

            # 3. Stage 1 Eval: Deterministic Schema Validation
            self._transition_to(NodeStatus.EVALUATING, stage="schema_validation", attempt=attempt + 1)
            parsed_output, parse_error = self._validate_schema(raw_response)
            if parse_error:
                feedback_notes.append(f"Schema Validation Error: {parse_error}. Please adhere strictly to the schema.")
                continue

            # 4. Stage 2 Eval: Semantic Definition of Done (DoD) Evaluation
            if self.dod_evaluator and parsed_output is not None:
                self._transition_to(NodeStatus.EVALUATING, stage="dod_semantic_eval", attempt=attempt + 1)
                dod_result = self.dod_evaluator(parsed_output, state)
                if not dod_result.is_met:
                    feedback_notes.extend(dod_result.feedback)
                    continue

            # Success: output meets both Schema and DoD
            response_content = str(raw_response) if parsed_output is None else parsed_output.model_dump_json()
            return {
                "messages": WorkflowMessage(role="assistant", content=response_content, name=self.name),
                "dod_evaluation": {"status": "PASSED", "attempts": attempt + 1},
                "execution_status": ExecutionStatus.RUNNING,
                "step_count": 1,
            }

        # Exhausted retries without meeting DoD
        self._transition_to(
            NodeStatus.FAILED,
            attempt=self.max_self_retries + 1,
            reasons=feedback_notes,
            message=f"Node '{self.name}' exhausted all {self.max_self_retries + 1} attempts.",
        )
        return {
            "execution_status": ExecutionStatus.FAILED,
            "error_message": f"Node '{self.name}' failed to meet DoD after {self.max_self_retries + 1} attempts.",
            "dod_evaluation": {"status": "FAILED", "feedback": feedback_notes},
            "step_count": 1,
        }

    async def _invoke_llm(self, prompt: str, messages: list[WorkflowMessage]) -> Any:
        import inspect
        res = self.llm_invoker(prompt, messages, self.skills)
        if inspect.isawaitable(res):
            return await res
        return res

    def _validate_schema(self, response: Any) -> tuple[Optional[BaseModel], Optional[str]]:
        if not self.output_schema:
            return None, None
        try:
            if isinstance(response, self.output_schema):
                return response, None
            if isinstance(response, dict):
                return self.output_schema.model_validate(response), None
            if isinstance(response, str):
                return self.output_schema.model_validate_json(response), None
            return None, f"Unsupported response type for schema parsing: {type(response)}"
        except ValidationError as e:
            return None, str(e)
