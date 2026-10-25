from __future__ import annotations

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from aiogram_fsm_inspector.event_bus import EventBus
from aiogram_fsm_inspector.snapshots import SnapshotManager
from aiogram_fsm_inspector.storage import DevToolsStorageProxy


@pytest.mark.asyncio
async def test_snapshot_lifecycle(tmp_path):
    filepath = tmp_path / "presets.json"
    manager = SnapshotManager(filepath=filepath)

    # 1. Save preset
    preset = manager.save_preset(
        name="Cart with Promo",
        state="Checkout:confirm",
        data={"cart": [101, 102], "promo": "SALE50"},
    )
    assert preset["name"] == "Cart with Promo"
    preset_id = preset["id"]

    # 2. List presets
    all_presets = manager.list_presets()
    assert len(all_presets) == 1
    assert all_presets[0]["id"] == preset_id

    # 3. Apply preset to a storage key
    bus = EventBus()
    storage = DevToolsStorageProxy(MemoryStorage(), bus=bus)
    key = StorageKey(bot_id=1, chat_id=123, user_id=456)

    applied = await manager.apply_preset(preset_id, key=key, storage_proxy=storage)
    assert applied is not None
    assert await storage.get_state(key) == "Checkout:confirm"
    data = await storage.get_data(key)
    assert data["promo"] == "SALE50"

    # 4. Delete preset
    deleted = manager.delete_preset(preset_id)
    assert deleted is True
    assert len(manager.list_presets()) == 0
