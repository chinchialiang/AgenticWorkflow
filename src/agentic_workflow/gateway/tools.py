"""Tool registry and sandboxed execution gateway."""

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """Metadata and execution pointer for an enterprise tool."""
    name: str
    description: str
    function: Callable[..., Any]
    is_mutating: bool = False
    requires_approval: bool = False


class ToolRegistry:
    """Enterprise Tool Registry for managing permissions, discovery, and execution."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        is_mutating: bool = False,
        requires_approval: bool = False,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register a tool function."""
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._tools[name] = ToolDefinition(
                name=name,
                description=description,
                function=func,
                is_mutating=is_mutating,
                requires_approval=requires_approval,
            )
            return func
        return decorator

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())
