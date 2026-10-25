from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from aiogram.fsm.storage.base import StorageKey

from .event_bus import EventBus
from .middleware import DevToolsMiddleware
from .scanner import StateRegistry
from .security import TokenAuthValidator
from .server import WebSocketHub
from .serialization import (
    dict_to_storage_key,
    safe_json_dump_ready,
    storage_key_to_dict,
)
from .snapshots import SnapshotManager
from .storage import DevToolsStorageProxy

logger = logging.getLogger("aiogram_fsm_inspector.app")

STATIC_DIR = Path(__file__).parent / "static"


# ─── Pydantic Request Models ───

class StateUpdateRequest(BaseModel):
    state: Optional[str] = None


class PresetCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    state: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class PresetApplyRequest(BaseModel):
    chat_id: int
    user_id: int
    bot_id: Optional[int] = None
    thread_id: Optional[int] = None
    destiny: str = "default"


def create_devtools_app(
    storage_proxy: DevToolsStorageProxy,
    event_bus: EventBus,
    middleware: DevToolsMiddleware,
    state_registry: StateRegistry,
    snapshot_manager: SnapshotManager,
    ws_hub: WebSocketHub,
    auth_validator: TokenAuthValidator,
) -> FastAPI:
    """
    FastAPI application factory for aiogram-fsm-inspector.
    Mounts REST API, WebSocket pubsub, and the zero-build single-file SPA.
    """
    app = FastAPI(
        title="aiogram-fsm-inspector",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )

    # Enable CORS for local cross-origin development if needed
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Wire EventBus to WebSocket broadcast
    async def _on_bus_event(event_type: str, payload: Dict[str, Any]) -> None:
        await ws_hub.broadcast(event_type, payload)

    event_bus.subscribe(_on_bus_event)

    def _resolve_key(
        chat_id: int,
        user_id: int,
        bot_id: Optional[int] = None,
        thread_id: Optional[int] = None,
        destiny: str = "default",
        business_connection_id: Optional[str] = None,
    ) -> StorageKey:
        # Check existing keys first
        for k in storage_proxy.known_keys:
            if k.chat_id == chat_id and k.user_id == user_id:
                if (bot_id is None or k.bot_id == bot_id) and \
                   (thread_id is None or k.thread_id == thread_id) and \
                   (k.destiny == destiny) and \
                   (business_connection_id is None or getattr(k, "business_connection_id", None) == business_connection_id):
                    return k
        # Fallback to constructing new StorageKey
        resolved_bot_id = bot_id if bot_id is not None else 0
        try:
            return StorageKey(
                bot_id=resolved_bot_id,
                chat_id=chat_id,
                user_id=user_id,
                thread_id=thread_id,
                business_connection_id=business_connection_id,
                destiny=destiny,
            )
        except TypeError:
            return StorageKey(
                bot_id=resolved_bot_id,
                chat_id=chat_id,
                user_id=user_id,
                thread_id=thread_id,
                destiny=destiny,
            )

    async def _build_session_snapshot(key: StorageKey) -> Dict[str, Any]:
        state = await storage_proxy.get_state(key=key)
        data = await storage_proxy.get_data(key=key)
        user_meta = middleware.get_user_meta(key.user_id)
        history = storage_proxy.get_history(key)

        return {
            "key": storage_key_to_dict(key),
            "user_meta": user_meta,
            "fsm": {
                "current_state": state,
                "data": safe_json_dump_ready(data),
            },
            "history": history,
        }

    # ─── Frontend Route ───

    @app.get("/", response_class=HTMLResponse)
    async def serve_dashboard():
        html_file = STATIC_DIR / "index.html"
        if not html_file.exists():
            return HTMLResponse(
                "<h2>aiogram-fsm-inspector web UI is missing.</h2>",
                status_code=500,
            )
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))

    @app.get("/api/v1/info")
    async def get_server_info():
        """Returns server and bot metadata for multi-bot federation and auto-discovery."""
        bot_info = getattr(app.state, "bot_info", {})
        port = getattr(app.state, "port", None)
        return {
            "status": "ok",
            "name": "aiogram-fsm-inspector",
            "version": "0.1.0",
            "port": port,
            "bot": bot_info,
            "session_count": len(storage_proxy.known_keys),
        }

    # ─── REST Endpoints: Sessions ───

    @app.get(
        "/api/v1/sessions",
        dependencies=[Depends(auth_validator)],
    )
    async def list_sessions():
        """Returns snapshot cards for all discovered active sessions."""
        results: List[Dict[str, Any]] = []
        for key in storage_proxy.known_keys:
            snapshot = await _build_session_snapshot(key)
            results.append(snapshot)
        return results

    @app.get(
        "/api/v1/sessions/{chat_id}/{user_id}",
        dependencies=[Depends(auth_validator)],
    )
    async def get_session(
        chat_id: int,
        user_id: int,
        bot_id: Optional[int] = Query(None),
        thread_id: Optional[int] = Query(None),
        destiny: str = Query("default"),
        business_connection_id: Optional[str] = Query(None),
    ):
        """Returns details, current state, and full FSM data for a user."""
        key = _resolve_key(
            chat_id=chat_id,
            user_id=user_id,
            bot_id=bot_id,
            thread_id=thread_id,
            destiny=destiny,
            business_connection_id=business_connection_id,
        )
        return await _build_session_snapshot(key)

    @app.patch(
        "/api/v1/sessions/{chat_id}/{user_id}/state",
        dependencies=[Depends(auth_validator)],
    )
    async def update_session_state(
        chat_id: int,
        user_id: int,
        req: StateUpdateRequest,
        bot_id: Optional[int] = Query(None),
        thread_id: Optional[int] = Query(None),
        destiny: str = Query("default"),
        business_connection_id: Optional[str] = Query(None),
    ):
        """Force switches the user's FSM state directly."""
        key = _resolve_key(
            chat_id=chat_id,
            user_id=user_id,
            bot_id=bot_id,
            thread_id=thread_id,
            destiny=destiny,
            business_connection_id=business_connection_id,
        )
        await storage_proxy.set_state(key=key, state=req.state, source="devtools_ui")
        return {"status": "ok", "state": req.state}

    @app.put(
        "/api/v1/sessions/{chat_id}/{user_id}/data",
        dependencies=[Depends(auth_validator)],
    )
    async def update_session_data(
        chat_id: int,
        user_id: int,
        incoming_data: Dict[str, Any],
        bot_id: Optional[int] = Query(None),
        thread_id: Optional[int] = Query(None),
        destiny: str = Query("default"),
        business_connection_id: Optional[str] = Query(None),
    ):
        """Hot-edits user FSM data, preserving non-serializable objects."""
        key = _resolve_key(
            chat_id=chat_id,
            user_id=user_id,
            bot_id=bot_id,
            thread_id=thread_id,
            destiny=destiny,
            business_connection_id=business_connection_id,
        )
        merged = await storage_proxy.merge_data_from_ui(key=key, incoming_json=incoming_data)
        return {"status": "ok", "data": safe_json_dump_ready(merged)}

    @app.post(
        "/api/v1/sessions/{chat_id}/{user_id}/clear",
        dependencies=[Depends(auth_validator)],
    )
    async def clear_session(
        chat_id: int,
        user_id: int,
        bot_id: Optional[int] = Query(None),
        thread_id: Optional[int] = Query(None),
        destiny: str = Query("default"),
        business_connection_id: Optional[str] = Query(None),
    ):
        """Wipes FSM state and data for the session."""
        key = _resolve_key(
            chat_id=chat_id,
            user_id=user_id,
            bot_id=bot_id,
            thread_id=thread_id,
            destiny=destiny,
            business_connection_id=business_connection_id,
        )
        await storage_proxy.clear_session(key=key)
        return {"status": "ok"}

    @app.delete(
        "/api/v1/sessions/{chat_id}/{user_id}",
        dependencies=[Depends(auth_validator)],
    )
    async def delete_session(
        chat_id: int,
        user_id: int,
        bot_id: Optional[int] = Query(None),
        thread_id: Optional[int] = Query(None),
        destiny: str = Query("default"),
        business_connection_id: Optional[str] = Query(None),
    ):
        """Deletes session from known list and clears storage."""
        key = _resolve_key(
            chat_id=chat_id,
            user_id=user_id,
            bot_id=bot_id,
            thread_id=thread_id,
            destiny=destiny,
            business_connection_id=business_connection_id,
        )
        await storage_proxy.clear_session(key=key)
        storage_proxy.unregister_key(key)
        return {"status": "ok"}

    @app.post(
        "/api/v1/sessions/{chat_id}/{user_id}/rollback",
        dependencies=[Depends(auth_validator)],
    )
    async def rollback_session(
        chat_id: int,
        user_id: int,
        bot_id: Optional[int] = Query(None),
        thread_id: Optional[int] = Query(None),
        destiny: str = Query("default"),
        business_connection_id: Optional[str] = Query(None),
    ):
        """Rolls back state and data to previous snapshot in time-travel history."""
        key = _resolve_key(
            chat_id=chat_id,
            user_id=user_id,
            bot_id=bot_id,
            thread_id=thread_id,
            destiny=destiny,
            business_connection_id=business_connection_id,
        )
        restored = await storage_proxy.rollback(key=key)
        if not restored:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No rollback history available for this session",
            )
        return {"status": "ok", "restored": restored}

    # ─── REST Endpoints: State Tree ───

    @app.get(
        "/api/v1/states-tree",
        dependencies=[Depends(auth_validator)],
    )
    async def get_states_tree():
        """Returns all StatesGroup classes and their states discovered in runtime."""
        return state_registry.get_tree()

    # ─── REST Endpoints: Snapshots / Presets ───

    @app.get(
        "/api/v1/snapshots",
        dependencies=[Depends(auth_validator)],
    )
    async def list_snapshots():
        """Returns list of all saved presets."""
        return snapshot_manager.list_presets()

    @app.post(
        "/api/v1/snapshots",
        dependencies=[Depends(auth_validator)],
    )
    async def create_snapshot(req: PresetCreateRequest):
        """Saves a new preset to local JSON file."""
        preset = snapshot_manager.save_preset(
            name=req.name,
            state=req.state,
            data=req.data,
            description=req.description,
        )
        return preset

    @app.delete(
        "/api/v1/snapshots/{snapshot_id}",
        dependencies=[Depends(auth_validator)],
    )
    async def delete_snapshot(snapshot_id: str):
        success = snapshot_manager.delete_preset(snapshot_id)
        if not success:
            raise HTTPException(status_code=404, detail="Preset not found")
        return {"status": "ok"}

    @app.post(
        "/api/v1/snapshots/{snapshot_id}/apply",
        dependencies=[Depends(auth_validator)],
    )
    async def apply_snapshot(snapshot_id: str, req: PresetApplyRequest):
        key = _resolve_key(
            chat_id=req.chat_id,
            user_id=req.user_id,
            bot_id=req.bot_id,
            thread_id=req.thread_id,
            destiny=req.destiny,
        )
        result = await snapshot_manager.apply_preset(
            preset_id=snapshot_id,
            key=key,
            storage_proxy=storage_proxy,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Preset not found")
        return {"status": "ok", "preset": result}

    # ─── WebSocket Endpoint ───

    @app.websocket("/api/v1/ws")
    async def websocket_endpoint(
        websocket: WebSocket,
        token: Optional[str] = Query(None),
    ):
        if not auth_validator.validate_ws_token(token):
            await websocket.close(code=4401, reason="Unauthorized")
            return

        await ws_hub.connect(websocket)

        # Send initial sync
        try:
            sessions_list: List[Dict[str, Any]] = []
            for k in storage_proxy.known_keys:
                sessions_list.append(await _build_session_snapshot(k))

            init_payload = {
                "bot": getattr(app.state, "bot_info", {}),
                "port": getattr(app.state, "port", None),
                "sessions": sessions_list,
                "states_tree": state_registry.get_tree(),
                "snapshots": snapshot_manager.list_presets(),
            }
            await websocket.send_json({"type": "INIT_SYNC", "payload": init_payload})

            # Keep socket alive and handle incoming client commands if any
            while True:
                msg = await websocket.receive_json()
                msg_type = msg.get("type")
                if msg_type == "PING":
                    await websocket.send_json({"type": "PONG", "payload": {}})
        except (WebSocketDisconnect, Exception) as exc:
            logger.debug("WebSocket client closed: %s", exc)
        finally:
            await ws_hub.disconnect(websocket)

    return app
