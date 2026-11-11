"""Cognitive / LLM node implementation with System Prompt, Skills, DoD, and Eval."""

import logging
from typing import Any, Callable, Optional, Type
from pydantic import BaseModel, ValidationError

from agentic_workflow.domain.models import DoDResult, ExecutionStatus, WorkflowMessage
from agentic_workflow.domain.state import AgentWorkflowState
from agentic_workflow.nodes.base import GraphNode

logger = logging.getLogger(__name__)


class CognitiveNode(GraphNode[AgentWorkflowState]):
    """Stochastic LLM node governed by an enterprise contract:
    - System Prompt: Role definition and invariants
    - Skills: Scoped tool registry for this node
    - DoD (Definition of Done): Formal Pydantic schema contract
    - Eval: Dual-stage validation (deterministic schema + semantic DoD check)
    - Self-correction retry loop
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

    async def execute(self, state: AgentWorkflowState) -> dict[str, Any]:
        messages = list(state.get("messages") or [])
        feedback_notes: list[str] = []

        for attempt in range(self.max_self_retries + 1):
            logger.info("Executing CognitiveNode '%s' (attempt %d/%d)", self.name, attempt + 1, self.max_self_retries + 1)

            # 1. Compile prompt with feedback if retrying
            augmented_prompt = self.system_prompt
            if feedback_notes:
                augmented_prompt += "\n\n[Evaluation Feedback from Previous Attempt]:\n" + "\n".join(feedback_notes)

            # 2. Invoke LLM
            raw_response = await self._invoke_llm(augmented_prompt, messages)

            # 3. Stage 1 Eval: Deterministic Schema Validation
            parsed_output, parse_error = self._validate_schema(raw_response)
            if parse_error:
                logger.warning("Stage 1 Eval failed for node '%s': %s", self.name, parse_error)
                feedback_notes.append(f"Schema Validation Error: {parse_error}. Please adhere strictly to the schema.")
                continue

            # 4. Stage 2 Eval: Semantic Definition of Done (DoD) Evaluation
            if self.dod_evaluator and parsed_output is not None:
                dod_result = self.dod_evaluator(parsed_output, state)
                if not dod_result.is_met:
                    logger.warning("Stage 2 Eval (DoD) failed for node '%s': %s", self.name, dod_result.feedback)
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
        logger.error("Node '%s' failed to satisfy DoD after %d attempts", self.name, self.max_self_retries + 1)
        return {
            "execution_status": ExecutionStatus.FAILED,
            "error_message": f"Node '{self.name}' failed to meet DoD after {self.max_self_retries + 1} attempts.",
            "dod_evaluation": {"status": "FAILED", "feedback": feedback_notes},
            "step_count": 1,
        }

    async def _invoke_llm(self, prompt: str, messages: list[WorkflowMessage]) -> Any:
        # Calls the injected LLM invoker (can be async or sync)
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
