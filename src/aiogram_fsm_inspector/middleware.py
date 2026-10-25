from __future__ import annotations

import collections
import logging
import time
import traceback
from typing import Any, Awaitable, Callable, Dict, Optional, OrderedDict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, User

from .event_bus import EventBus

logger = logging.getLogger("aiogram_fsm_inspector.middleware")


class DevToolsMiddleware(BaseMiddleware):
    """
    Outer middleware registered on dp.update.outer_middleware.
    Extracts user metadata, measures handler execution performance,
    and captures unhandled errors along with their execution tracebacks.
    """

    def __init__(self, bus: EventBus, max_users: int = 2000) -> None:
        self._bus = bus
        self._max_users = max_users
        self._user_meta: OrderedDict[int, Dict[str, Any]] = collections.OrderedDict()

    def get_user_meta(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves stored metadata for a given Telegram user ID."""
        return self._user_meta.get(user_id)

    def get_all_user_meta(self) -> Dict[int, Dict[str, Any]]:
        """Returns all cached user metadata."""
        return dict(self._user_meta)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        start_time = time.perf_counter()

        # Extract user if available
        user: Optional[User] = data.get("event_from_user")
        if not user:
            # Fallback to inspecting event attributes
            user = getattr(event, "from_user", None)
            if not user and isinstance(event, Update):
                actual_event = (
                    event.message
                    or event.callback_query
                    or event.inline_query
                    or event.chosen_inline_result
                    or event.my_chat_member
                    or event.chat_member
                    or event.chat_join_request
                )
                if actual_event:
                    user = getattr(actual_event, "from_user", None)

        user_id = user.id if user else None
        event_type = event.event_type if isinstance(event, Update) else event.__class__.__name__

        if user and user_id:
            meta = {
                "user_id": user_id,
                "username": user.username,
                "full_name": user.full_name,
                "language_code": user.language_code,
                "is_bot": user.is_bot,
                "is_premium": getattr(user, "is_premium", False),
                "last_active_at": time.time(),
                "last_event_type": event_type,
            }
            self._user_meta[user_id] = meta
            self._user_meta.move_to_end(user_id)
            while len(self._user_meta) > self._max_users:
                self._user_meta.popitem(last=False)

        try:
            result = await handler(event, data)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            await self._bus.publish(
                "HANDLER_EXECUTED",
                {
                    "user_id": user_id,
                    "duration_ms": duration_ms,
                    "event_type": event_type,
                    "timestamp": time.time(),
                },
            )
            return result
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            formatted_tb = traceback.format_exc()
            logger.debug("Captured handler error for user %s: %s", user_id, exc)
            await self._bus.publish(
                "HANDLER_ERROR",
                {
                    "user_id": user_id,
                    "duration_ms": duration_ms,
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                    "traceback": formatted_tb,
                    "event_type": event_type,
                    "timestamp": time.time(),
                },
            )
            # Re-raise so aiogram error handlers and loggers function as expected
            raise exc
