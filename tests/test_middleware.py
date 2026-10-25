from __future__ import annotations

import pytest
from aiogram.types import User

from aiogram_fsm_inspector.event_bus import EventBus
from aiogram_fsm_inspector.middleware import DevToolsMiddleware


class MockEvent:
    event_type = "message"


@pytest.mark.asyncio
async def test_middleware_successful_execution():
    events = []

    async def on_event(event_type: str, payload: dict):
        events.append((event_type, payload))

    bus = EventBus()
    bus.subscribe(on_event)
    middleware = DevToolsMiddleware(bus=bus)

    user = User(id=999, is_bot=False, first_name="Test", username="testuser")
    data = {"event_from_user": user}

    async def sample_handler(event, d):
        return "handler_result"

    res = await middleware(sample_handler, MockEvent(), data)
    assert res == "handler_result"

    meta = middleware.get_user_meta(999)
    assert meta is not None
    assert meta["username"] == "testuser"

    assert len(events) == 1
    assert events[0][0] == "HANDLER_EXECUTED"
    assert events[0][1]["user_id"] == 999
    assert events[0][1]["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_middleware_error_capture():
    events = []

    async def on_event(event_type: str, payload: dict):
        events.append((event_type, payload))

    bus = EventBus()
    bus.subscribe(on_event)
    middleware = DevToolsMiddleware(bus=bus)

    user = User(id=888, is_bot=False, first_name="ErrorUser")
    data = {"event_from_user": user}

    async def faulty_handler(event, d):
        raise ValueError("Simulated handler crash")

    with pytest.raises(ValueError, match="Simulated handler crash"):
        await middleware(faulty_handler, MockEvent(), data)

    assert len(events) == 1
    assert events[0][0] == "HANDLER_ERROR"
    assert events[0][1]["user_id"] == 888
    assert events[0][1]["error_type"] == "ValueError"
    assert "Simulated handler crash" in events[0][1]["error_message"]
    assert "Traceback" in events[0][1]["traceback"]
