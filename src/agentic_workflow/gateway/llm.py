"""LLM Gateway abstraction and mock providers for testing."""

from typing import Any, Protocol
from agentic_workflow.domain.models import WorkflowMessage


class LLMInvokerProtocol(Protocol):
    """Protocol for LLM invoker functions or classes."""

    async def __call__(
        self,
        system_prompt: str,
        messages: list[WorkflowMessage],
        tools: list[Any],
    ) -> Any:
        ...


class MockLLMInvoker:
    """Mock invoker for deterministic testing without external API credentials."""

    def __init__(self, canned_response: Any):
        self.canned_response = canned_response
        self.invocation_count = 0

    async def __call__(
        self,
        system_prompt: str,
        messages: list[WorkflowMessage],
        tools: list[Any],
    ) -> Any:
        self.invocation_count += 1
        if callable(self.canned_response):
            return self.canned_response(self.invocation_count)
        return self.canned_response
