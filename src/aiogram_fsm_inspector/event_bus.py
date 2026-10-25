from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List, Set

logger = logging.getLogger("aiogram_fsm_inspector.event_bus")

EventHandler = Callable[[str, Dict[str, Any]], Awaitable[None]]


class EventBus:
    """
    Asynchronous event bus implementing the Observer pattern.
    Distributes events (state changes, data modifications, audit logs) to registered subscribers.
    """

    def __init__(self) -> None:
        self._subscribers: Set[EventHandler] = set()
        self._lock = asyncio.Lock()

    def subscribe(self, handler: EventHandler) -> None:
        """Register an async callback for incoming events."""
        self._subscribers.add(handler)

    def unsubscribe(self, handler: EventHandler) -> None:
        """Remove an async callback from subscribers."""
        self._subscribers.discard(handler)

    async def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Publish an event to all subscribers concurrently.
        Catches and logs any individual subscriber errors to prevent interrupting callers.
        """
        if not self._subscribers:
            return

        tasks: List[asyncio.Task[Any]] = []
        for handler in list(self._subscribers):
            tasks.append(asyncio.create_task(self._safe_invoke(handler, event_type, payload)))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_invoke(
        self,
        handler: EventHandler,
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        try:
            await handler(event_type, payload)
        except Exception as exc:
            logger.warning("Error in event subscriber %s: %s", getattr(handler, "__name__", repr(handler)), exc)
