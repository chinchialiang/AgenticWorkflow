"""LLM Gateway abstraction, response normalization, and mock providers for testing."""

from typing import Any, Optional, Protocol
from agentic_workflow.domain.models import LLMResponse, LLMUsage, WorkflowMessage


class LLMInvokerProtocol(Protocol):
    """Protocol for LLM invoker functions or classes."""

    async def __call__(
        self,
        system_prompt: str,
        messages: list[WorkflowMessage],
        tools: list[Any],
    ) -> Any:
        ...


def normalize_llm_response(raw: Any, default_model_id: Optional[str] = None) -> LLMResponse:
    """Normalizes raw invoker outputs (str, dict, BaseModel, or LLMResponse) into LLMResponse."""
    if isinstance(raw, LLMResponse):
        if default_model_id and not raw.usage.model_id:
            raw.usage.model_id = default_model_id
        return raw
    return LLMResponse(
        content=raw,
        usage=LLMUsage(model_id=default_model_id),
    )


class MockLLMInvoker:
    """Mock invoker for deterministic testing without external API credentials."""

    def __init__(self, canned_response: Any, usage: Optional[LLMUsage] = None):
        self.canned_response = canned_response
        self.usage = usage
        self.invocation_count = 0
        self.last_system_prompt: Optional[str] = None
        self.last_messages: list[WorkflowMessage] = []
        self.last_tools: list[Any] = []

    async def __call__(
        self,
        system_prompt: str,
        messages: list[WorkflowMessage],
        tools: list[Any],
    ) -> Any:
        self.invocation_count += 1
        self.last_system_prompt = system_prompt
        self.last_messages = list(messages)
        self.last_tools = list(tools)

        payload = (
            self.canned_response(self.invocation_count)
            if callable(self.canned_response)
            else self.canned_response
        )
        if self.usage is not None and not isinstance(payload, LLMResponse):
            return LLMResponse(content=payload, usage=self.usage)
        return payload
