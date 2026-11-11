"""Streaming listener for real-time node state and token streaming."""

import asyncio
from typing import AsyncGenerator, Dict, List, Optional
from agentic_workflow.core.events import WorkflowEvent, WorkflowEventListener, WorkflowEventType


class NodeStateStreamListener(WorkflowEventListener):
    """Listens for node state transitions and provides an async stream (SSE/WebSocket friendly).
    Decoupled from HTTP requests: clients can subscribe at any time.
    """

    def __init__(self, history_buffer_size: int = 100):
        self._history_buffer_size = history_buffer_size
        self._queues: Dict[str, List[asyncio.Queue[WorkflowEvent]]] = {}
        self._history: Dict[str, List[WorkflowEvent]] = {}

    async def on_event(self, event: WorkflowEvent) -> None:
        thread_id = event.thread_id

        # 1. Append to historical circular buffer for new subscriber replay
        if thread_id not in self._history:
            self._history[thread_id] = []
        history_list = self._history[thread_id]
        history_list.append(event)
        if len(history_list) > self._history_buffer_size:
            history_list.pop(0)

        # 2. Push to all active subscriber queues for this thread
        if thread_id in self._queues:
            for queue in self._queues[thread_id]:
                await queue.put(event)

    async def stream_events(
        self,
        thread_id: str,
        replay_history: bool = True,
    ) -> AsyncGenerator[WorkflowEvent, None]:
        """Async generator yielding real-time events for SSE or WebSocket streaming."""
        queue: asyncio.Queue[WorkflowEvent] = asyncio.Queue()

        if thread_id not in self._queues:
            self._queues[thread_id] = []
        self._queues[thread_id].append(queue)

        try:
            # Replay historical events if requested
            if replay_history and thread_id in self._history:
                for past_event in self._history[thread_id]:
                    yield past_event
                    if past_event.event_type in (
                        WorkflowEventType.GRAPH_COMPLETED,
                        WorkflowEventType.GRAPH_FAILED,
                    ):
                        return

            # Yield live events as they arrive
            while True:
                event = await queue.get()
                yield event
                queue.task_done()
                if event.event_type in (
                    WorkflowEventType.GRAPH_COMPLETED,
                    WorkflowEventType.GRAPH_FAILED,
                ):
                    break
        finally:
            if thread_id in self._queues and queue in self._queues[thread_id]:
                self._queues[thread_id].remove(queue)
                if not self._queues[thread_id]:
                    del self._queues[thread_id]
