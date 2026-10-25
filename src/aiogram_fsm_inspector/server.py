from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any, Dict, List, Optional, Set

import uvicorn
from aiogram import Dispatcher
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .security import validate_host_security

logger = logging.getLogger("aiogram_fsm_inspector.server")


class EmbeddedUvicornServer(uvicorn.Server):
    """
    Uvicorn server specialized for execution within an existing asyncio event loop.
    Disables OS signal handlers (SIGINT, SIGTERM) so aiogram Dispatcher
    maintains full control over process lifecycle and polling shutdown.
    """

    def install_signal_handlers(self) -> None:
        pass


class WebSocketHub:
    """
    Manages active WebSocket connections with concurrent-safe broadcast
    and automatic eviction of closed/stale client sockets.
    """

    def __init__(self) -> None:
        self._active_sockets: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def client_count(self) -> int:
        return len(self._active_sockets)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._active_sockets.add(websocket)
        logger.debug("DevTools WebSocket client connected. Active: %d", len(self._active_sockets))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._active_sockets.discard(websocket)
        logger.debug("DevTools WebSocket client disconnected. Active: %d", len(self._active_sockets))

    async def broadcast(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Sends an event to all connected browsers. Discarding broken sockets gracefully.
        """
        message = {"type": event_type, "payload": payload}

        async with self._lock:
            sockets_list: List[WebSocket] = list(self._active_sockets)

        if not sockets_list:
            return

        stale_sockets: List[WebSocket] = []
        for ws in sockets_list:
            try:
                await asyncio.wait_for(ws.send_json(message), timeout=2.0)
            except (WebSocketDisconnect, RuntimeError, asyncio.TimeoutError, Exception) as exc:
                logger.debug("Client websocket write failed (%s), marking stale", exc)
                stale_sockets.append(ws)

        if stale_sockets:
            async with self._lock:
                for ws in stale_sockets:
                    self._active_sockets.discard(ws)

    async def close_all(self, code: int = 1001, reason: str = "Server shutdown") -> None:
        """Closes all active websocket connections promptly."""
        async with self._lock:
            sockets = list(self._active_sockets)
            self._active_sockets.clear()

        for ws in sockets:
            try:
                await asyncio.wait_for(ws.close(code=code, reason=reason), timeout=1.0)
            except Exception:
                pass


def find_available_port(host: str, start_port: int, max_attempts: int = 30) -> int:
    """Finds the next available TCP port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    return start_port


class DevToolsServerManager:
    """
    Integrates the Uvicorn ASGI server into aiogram's startup and shutdown lifecycle.
    """

    def __init__(
        self,
        app: FastAPI,
        host: str = "127.0.0.1",
        port: int = 8080,
        log_level: str = "warning",
        auth_token: Optional[str] = None,
        ws_hub: Optional[WebSocketHub] = None,
        auto_port: bool = True,
    ) -> None:
        self.app = app
        self.host = host
        if auto_port and host in ("127.0.0.1", "localhost", "0.0.0.0"):
            actual_port = find_available_port(self.host, port)
            if actual_port != port:
                logger.warning(
                    "Port %d is already in use. aiogram-devtools will listen on port %d instead.",
                    port,
                    actual_port,
                )
            self.port = actual_port
        else:
            self.port = port

        self.log_level = log_level
        self.auth_token = auth_token
        self.ws_hub = ws_hub

        self.app.state.port = self.port
        self.app.state.bot_info = {}

        validate_host_security(self.host, self.auth_token)

        self._server: Optional[EmbeddedUvicornServer] = None
        self._task: Optional[asyncio.Task[None]] = None

    def attach_to_dispatcher(self, dp: Dispatcher) -> None:
        """Hooks Uvicorn start and graceful stop into the Dispatcher."""
        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level=self.log_level,
            loop="none",  # Re-use currently running asyncio loop
            lifespan="off",
        )
        self._server = EmbeddedUvicornServer(config=config)

        @dp.startup()
        async def _start_devtools(bot: Optional[Any] = None, *args, **kwargs) -> None:
            if bot:
                try:
                    me = await bot.get_me()
                    self.app.state.bot_info = {
                        "id": me.id,
                        "username": me.username,
                        "first_name": me.first_name,
                        "is_bot": me.is_bot,
                    }
                except Exception:
                    self.app.state.bot_info = {"id": getattr(bot, "id", None), "username": None}

            logger.info("Starting aiogram-devtools server on http://%s:%d", self.host, self.port)
            self._task = asyncio.create_task(
                self._server.serve(),
                name="aiogram-devtools-server",
            )

        @dp.shutdown()
        async def _stop_devtools(*args, **kwargs) -> None:
            logger.info("Stopping aiogram-devtools server...")
            if self.ws_hub:
                try:
                    await self.ws_hub.close_all()
                except Exception as exc:
                    logger.debug("Error closing websockets during shutdown: %s", exc)
            if self._server:
                self._server.should_exit = True
            if self._task:
                try:
                    await asyncio.wait_for(self._task, timeout=5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    self._task.cancel()
            logger.info("aiogram-devtools server stopped.")
