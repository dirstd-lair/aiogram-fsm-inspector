from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from aiogram_fsm_inspector.security import SecurityError, validate_host_security
from aiogram_fsm_inspector.setup import setup_devtools
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import Dispatcher


def test_validate_host_security():
    # Loopback passes without token
    validate_host_security("127.0.0.1")
    validate_host_security("localhost")

    # 0.0.0.0 without token or env var raises SecurityError
    os.environ.pop("AIOGRAM_DEVTOOLS_UNSAFE", None)
    with pytest.raises(SecurityError, match="is prohibited"):
        validate_host_security("0.0.0.0")

    # 0.0.0.0 with token passes
    validate_host_security("0.0.0.0", auth_token="my_token")

    # 0.0.0.0 with env var passes
    os.environ["AIOGRAM_DEVTOOLS_UNSAFE"] = "1"
    validate_host_security("0.0.0.0")
    os.environ.pop("AIOGRAM_DEVTOOLS_UNSAFE", None)


def test_token_auth_api(tmp_path):
    dp = Dispatcher(storage=MemoryStorage())
    bundle = setup_devtools(
        dp,
        host="127.0.0.1",
        port=8080,
        auth_token="secret123",
        snapshots_path=tmp_path / "snaps.json",
    )
    client = TestClient(bundle.app)

    # 1. No auth -> 401
    res = client.get("/api/v1/sessions")
    assert res.status_code == 401

    # 2. Wrong token -> 401
    res = client.get("/api/v1/sessions", headers={"Authorization": "Bearer wrong"})
    assert res.status_code == 401

    # 3. Correct Bearer token -> 200
    res = client.get("/api/v1/sessions", headers={"Authorization": "Bearer secret123"})
    assert res.status_code == 200

    # 4. Correct query param -> 200
    res = client.get("/api/v1/sessions?token=secret123")
    assert res.status_code == 200

    # 5. WebSocket auth rejection
    with pytest.raises(Exception):
        with client.websocket_connect("/api/v1/ws?token=wrong"):
            pass

    # 6. WebSocket auth success
    with client.websocket_connect("/api/v1/ws?token=secret123") as ws:
        init = ws.receive_json()
        assert init["type"] == "INIT_SYNC"
