from __future__ import annotations

import pytest
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from aiogram_fsm_inspector.event_bus import EventBus
from aiogram_fsm_inspector.storage import DevToolsStorageProxy


class OrderForm(StatesGroup):
    name = State()
    phone = State()


@pytest.mark.asyncio
async def test_storage_proxy_state_and_events():
    events = []

    async def on_event(event_type: str, payload: dict):
        events.append((event_type, payload))

    bus = EventBus()
    bus.subscribe(on_event)

    raw_storage = MemoryStorage()
    proxy = DevToolsStorageProxy(raw_storage, bus=bus)

    key = StorageKey(bot_id=1, chat_id=100, user_id=200)

    # 1. Test set_state with string
    await proxy.set_state(key, "OrderForm:name")
    assert await proxy.get_state(key) == "OrderForm:name"
    assert len(events) == 1
    assert events[0][0] == "STATE_UPDATED"
    assert events[0][1]["state"] == "OrderForm:name"
    assert key in proxy.known_keys

    # 2. Test set_state with State object
    state_obj = OrderForm.phone
    await proxy.set_state(key, state_obj)
    assert await proxy.get_state(key) == "OrderForm:phone"
    assert len(events) == 2
    assert events[1][1]["state"] == "OrderForm:phone"

    # 3. Test set_data
    await proxy.set_data(key, {"phone": "+123456789"})
    data = await proxy.get_data(key)
    assert data["phone"] == "+123456789"
    assert len(events) == 3
    assert events[2][0] == "DATA_UPDATED"
    assert events[2][1]["data"]["phone"] == "+123456789"

    # 4. Critical: Test update_data emits DATA_UPDATED
    await proxy.update_data(key, {"address": "Baker St."})
    data = await proxy.get_data(key)
    assert data["phone"] == "+123456789"
    assert data["address"] == "Baker St."
    assert len(events) == 4
    assert events[3][0] == "DATA_UPDATED"
    assert events[3][1]["data"]["address"] == "Baker St."


@pytest.mark.asyncio
async def test_storage_proxy_time_travel_rollback():
    bus = EventBus()
    raw_storage = MemoryStorage()
    proxy = DevToolsStorageProxy(raw_storage, bus=bus)
    key = StorageKey(bot_id=1, chat_id=10, user_id=20)

    # Step 1
    await proxy.set_state(key, "Step1")
    await proxy.set_data(key, {"val": 1})

    # Step 2
    await proxy.set_state(key, "Step2")
    await proxy.update_data(key, {"val": 2})

    # Step 3
    await proxy.set_state(key, "Step3")
    await proxy.update_data(key, {"val": 3})

    history = proxy.get_history(key)
    assert len(history) >= 3

    # Rollback to Step 2
    restored = await proxy.rollback(key)
    assert restored is not None
    assert restored["state"] == "Step2"
    assert (await proxy.get_state(key)) == "Step2"
    assert (await proxy.get_data(key))["val"] == 2


@pytest.mark.asyncio
async def test_storage_proxy_clear_session():
    bus = EventBus()
    raw_storage = MemoryStorage()
    proxy = DevToolsStorageProxy(raw_storage, bus=bus)
    key = StorageKey(bot_id=1, chat_id=50, user_id=60)

    await proxy.set_state(key, "Active")
    await proxy.set_data(key, {"token": "abc"})

    await proxy.clear_session(key)
    assert await proxy.get_state(key) is None
    assert await proxy.get_data(key) == {}


@pytest.mark.asyncio
async def test_storage_proxy_lru_eviction():
    bus = EventBus()
    raw_storage = MemoryStorage()
    proxy = DevToolsStorageProxy(raw_storage, bus=bus, max_sessions=3)

    k1 = StorageKey(bot_id=1, chat_id=1, user_id=1)
    k2 = StorageKey(bot_id=1, chat_id=2, user_id=2)
    k3 = StorageKey(bot_id=1, chat_id=3, user_id=3)
    k4 = StorageKey(bot_id=1, chat_id=4, user_id=4)

    await proxy.set_state(k1, "S1")
    await proxy.set_state(k2, "S2")
    await proxy.set_state(k3, "S3")

    assert proxy.known_keys == {k1, k2, k3}

    # Registering 4th key should evict oldest (k1)
    await proxy.set_state(k4, "S4")
    assert proxy.known_keys == {k2, k3, k4}
    assert k1 not in proxy.known_keys
    assert len(proxy.get_history(k1)) == 0
