"""Deterministic state reducers (CQRS event-sourcing style)."""

from typing import Any, Sequence
from agentic_workflow.domain.models import WorkflowMessage


def append_messages(
    current: Sequence[WorkflowMessage] | None,
    new_messages: Sequence[WorkflowMessage] | WorkflowMessage | None,
) -> list[WorkflowMessage]:
    """Pure reducer that appends new messages to the existing sequence."""
    base = list(current or [])
    if new_messages is None:
        return base
    if isinstance(new_messages, WorkflowMessage):
        return base + [new_messages]
    return base + list(new_messages)


def increment_counter(current: int | None, increment_by: int = 1) -> int:
    """Pure reducer that increments a numeric counter."""
    return (current or 0) + increment_by


def merge_dicts(current: dict[str, Any] | None, update: dict[str, Any] | None) -> dict[str, Any]:
    """Pure reducer that merges two dictionaries without mutating the original."""
    result = dict(current or {})
    if update:
        result.update(update)
    return result
