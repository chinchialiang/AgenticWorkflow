"""Base abstraction for all workflow nodes."""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar
import logging

logger = logging.getLogger(__name__)

TState = TypeVar("TState")


class GraphNode(ABC, Generic[TState]):
    """Abstract base class for all nodes in the state graph.
    Similar to a Spring Command Handler or Camel Processor.
    """

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def execute(self, state: TState) -> dict[str, Any]:
        """Core execution logic. Receives the immutable state and returns a state delta."""
        pass

    async def __call__(self, state: TState) -> dict[str, Any]:
        """Callable interface matching LangGraph node requirements."""
        logger.debug("Entering node: %s", self.name)
        delta = await self.execute(state)
        # Always track current_node in control state
        if isinstance(delta, dict) and "current_node" not in delta:
            delta["current_node"] = self.name
        return delta
