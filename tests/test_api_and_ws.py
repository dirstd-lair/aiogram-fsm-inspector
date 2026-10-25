from __future__ import annotations

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from fastapi.testclient import TestClient

from aiogram_fsm_inspector.app import create_devtools_app
from aiogram_fsm_inspector.event_bus import EventBus
from aiogram_fsm_inspector.middleware import DevToolsMiddleware
from aiogram_fsm_inspector.scanner import StateRegistry
from aiogram_fsm_inspector.security import TokenAuthValidator
from aiogram_fsm_inspector.server import WebSocketHub
from aiogram_fsm_inspector.snapshots import SnapshotManager
from aiogram_fsm_inspector.storage import DevToolsStorageProxy


@pytest.fixture
def test_app_and_proxy(tmp_path):
    bus = EventBus()
    storage = DevToolsStorageProxy(MemoryStorage(), bus=bus)
    middleware = DevToolsMiddleware(bus=bus)
    scanner = StateRegistry()
    scanner.scan()
    snapshots = SnapshotManager(filepath=tmp_path / "test_snaps.json")
    ws_hub = WebSocketHub()
    auth = TokenAuthValidator(required_token=None)

    app = create_devtools_app(
        storage_proxy=storage,
        event_bus=bus,
        middleware=middleware,
        state_registry=scanner,
        snapshot_manager=snapshots,
        ws_hub=ws_hub,
        auth_validator=auth,
    )
    return app, storage, snapshots


def test_serve_dashboard_html(test_app_and_proxy):
    app, _, _ = test_app_and_proxy
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "aiogram-fsm-inspector" in response.text


def test_rest_api_sessions_and_mutations(test_app_and_proxy):
    app, storage, _ = test_app_and_proxy
    client = TestClient(app)

    # Initially empty
    res = client.get("/api/v1/sessions")
    assert res.status_code == 200
    assert res.json() == []

    # 1. State change via PATCH
    patch_res = client.patch(
        "/api/v1/sessions/100/200/state",
        json={"state": "TestForm:step_1"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["state"] == "TestForm:step_1"

    # Verify session is now listed
    res = client.get("/api/v1/sessions")
    assert len(res.json()) == 1
    session = res.json()[0]
    assert session["key"]["chat_id"] == 100
    assert session["key"]["user_id"] == 200
    assert session["fsm"]["current_state"] == "TestForm:step_1"

    # 2. Hot-edit data via PUT
    put_res = client.put(
        "/api/v1/sessions/100/200/data",
        json={"age": 25, "city": "Berlin"},
    )
    assert put_res.status_code == 200
    assert put_res.json()["data"]["age"] == 25

    # 3. Fetch single session detail
    detail_res = client.get("/api/v1/sessions/100/200")
    assert detail_res.status_code == 200
    assert detail_res.json()["fsm"]["data"]["city"] == "Berlin"

    # 4. Clear session via POST
    clear_res = client.post("/api/v1/sessions/100/200/clear")
    assert clear_res.status_code == 200

    detail_after_clear = client.get("/api/v1/sessions/100/200")
    assert detail_after_clear.json()["fsm"]["current_state"] is None
    assert detail_after_clear.json()["fsm"]["data"] == {}


def test_rest_api_states_tree(test_app_and_proxy):
    app, _, _ = test_app_and_proxy
    client = TestClient(app)
    res = client.get("/api/v1/states-tree")
    assert res.status_code == 200
    assert isinstance(res.json(), dict)


def test_rest_api_snapshots(test_app_and_proxy):
    app, _, _ = test_app_and_proxy
    client = TestClient(app)

    # Create preset
    create_res = client.post(
        "/api/v1/snapshots",
        json={"name": "Preset One", "state": "Form:ready", "data": {"qty": 5}},
    )
    assert create_res.status_code == 200
    preset_id = create_res.json()["id"]

    # List presets
    list_res = client.get("/api/v1/snapshots")
    assert len(list_res.json()) == 1

    # Apply preset
    apply_res = client.post(
        f"/api/v1/snapshots/{preset_id}/apply",
        json={"chat_id": 999, "user_id": 888},
    )
    assert apply_res.status_code == 200

    # Verify session now has preset state and data
    session_res = client.get("/api/v1/sessions/999/888")
    assert session_res.json()["fsm"]["current_state"] == "Form:ready"
    assert session_res.json()["fsm"]["data"]["qty"] == 5

    # Delete preset
    del_res = client.delete(f"/api/v1/snapshots/{preset_id}")
    assert del_res.status_code == 200
    assert len(client.get("/api/v1/snapshots").json()) == 0


def test_websocket_initial_sync(test_app_and_proxy):
    app, storage, _ = test_app_and_proxy
    client = TestClient(app)

    with client.websocket_connect("/api/v1/ws") as websocket:
        init_packet = websocket.receive_json()
        assert init_packet["type"] == "INIT_SYNC"
        assert "sessions" in init_packet["payload"]
        assert "states_tree" in init_packet["payload"]
        assert "snapshots" in init_packet["payload"]

        # Test PING/PONG
        websocket.send_json({"type": "PING"})
        pong = websocket.receive_json()
        assert pong["type"] == "PONG"


def test_sessions_with_thread_id_and_destiny(test_app_and_proxy):
    app, storage, _ = test_app_and_proxy
    client = TestClient(app)

    # Create two sessions in same chat for same user, but different threads/destiny
    k_thread1 = StorageKey(bot_id=1, chat_id=500, user_id=600, thread_id=10, destiny="default")
    k_thread2 = StorageKey(bot_id=1, chat_id=500, user_id=600, thread_id=20, destiny="default")

    client.patch(
        "/api/v1/sessions/500/600/state?thread_id=10",
        json={"state": "Thread10State"},
    )
    client.patch(
        "/api/v1/sessions/500/600/state?thread_id=20",
        json={"state": "Thread20State"},
    )

    res10 = client.get("/api/v1/sessions/500/600?thread_id=10")
    assert res10.status_code == 200
    assert res10.json()["fsm"]["current_state"] == "Thread10State"
    assert res10.json()["key"]["thread_id"] == 10

    res20 = client.get("/api/v1/sessions/500/600?thread_id=20")
    assert res20.status_code == 200
    assert res20.json()["fsm"]["current_state"] == "Thread20State"
    assert res20.json()["key"]["thread_id"] == 20
