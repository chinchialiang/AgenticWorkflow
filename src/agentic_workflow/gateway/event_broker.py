"""In-memory asynchronous event broker implementation using asyncio.Queue."""

import asyncio
import logging
from typing import Dict, List, Optional, Sequence, Set

from agentic_workflow.core.events import EventBroker, WorkflowEvent, WorkflowEventListener, WorkflowEventType

logger = logging.getLogger("agentic_workflow.gateway.broker")


class InMemoryAsyncEventBroker(EventBroker):
    """Production-grade In-Memory Event Broker.
    - Non-blocking async publishing via asyncio.Queue
    - Fan-out to multiple listeners concurrently
    - Event filtering by WorkflowEventType
    - Fault-isolated dispatching (one listener failure doesn't block others)
    """

    def __init__(self, queue_maxsize: int = 10000):
        self._queue: asyncio.Queue[Optional[WorkflowEvent]] = asyncio.Queue(maxsize=queue_maxsize)
        self._subscriptions: Dict[WorkflowEventListener, Optional[Set[WorkflowEventType]]] = {}
        self._worker_task: Optional[asyncio.Task] = None
        self._is_running: bool = False

    async def start(self) -> None:
        """Starts the background event dispatching worker."""
        if self._is_running:
            return
        self._is_running = True
        self._worker_task = asyncio.create_task(self._dispatch_loop())
        logger.info("InMemoryAsyncEventBroker started.")

    async def stop(self) -> None:
        """Gracefully drains and stops the broker."""
        if not self._is_running:
            return
        self._is_running = False
        await self._queue.put(None)  # Sentinel to unblock queue.get()
        if self._worker_task:
            await self._worker_task
        logger.info("InMemoryAsyncEventBroker stopped.")

    def subscribe(
        self,
        listener: WorkflowEventListener,
        event_types: Optional[Sequence[WorkflowEventType]] = None,
    ) -> None:
        """Registers a listener with optional event type filtering."""
        filters = set(event_types) if event_types else None
        self._subscriptions[listener] = filters
        logger.debug("Subscribed listener: %s (filters: %s)", type(listener).__name__, filters)

    def unsubscribe(self, listener: WorkflowEventListener) -> None:
        """Removes a listener registration."""
        self._subscriptions.pop(listener, None)

    async def publish(self, event: WorkflowEvent) -> None:
        """Publishes an event to the queue without blocking."""
        if not self._is_running:
            # If not explicitly started, start automatically
            await self.start()
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Event queue full! Dropping event %s (%s)", event.event_id, event.event_type)

    async def _dispatch_loop(self) -> None:
        """Background worker that continuously pulls events and fans out to listeners."""
        while self._is_running:
            try:
                event = await self._queue.get()
                if event is None:
                    # Sentinel received, exit loop
                    break

                # Fan-out to all matched listeners concurrently
                tasks = []
                for listener, filters in list(self._subscriptions.items()):
                    if filters is None or event.event_type in filters:
                        tasks.append(self._safely_call_listener(listener, event))

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Unexpected error in event dispatch loop: %s", exc)

    async def _safely_call_listener(
        self,
        listener: WorkflowEventListener,
        event: WorkflowEvent,
    ) -> None:
        """Calls an individual listener with exception isolation."""
        try:
            await listener.on_event(event)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception(
                "Listener '%s' failed handling event %s: %s",
                type(listener).__name__,
                event.event_type,
                exc,
            )
