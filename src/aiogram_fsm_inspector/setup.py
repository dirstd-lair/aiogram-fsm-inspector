from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from aiogram import Bot, Dispatcher
from fastapi import FastAPI

from .app import create_devtools_app
from .event_bus import EventBus
from .middleware import DevToolsMiddleware
from .scanner import StateRegistry
from .security import TokenAuthValidator
from .server import DevToolsServerManager, WebSocketHub
from .snapshots import SnapshotManager
from .storage import DevToolsStorageProxy

logger = logging.getLogger("aiogram_fsm_inspector")


@dataclass
class DevToolsBundle:
    """Holds references to all active inspector components."""
    app: FastAPI
    storage_proxy: DevToolsStorageProxy
    event_bus: EventBus
    middleware: DevToolsMiddleware
    state_registry: StateRegistry
    snapshot_manager: SnapshotManager
    server_manager: DevToolsServerManager
    ws_hub: WebSocketHub


def setup_devtools(
    dp: Dispatcher,
    host: str = "127.0.0.1",
    port: int = 8080,
    enabled: bool = True,
    auth_token: Optional[str] = None,
    log_level: str = "warning",
    max_history_per_user: int = 20,
    max_sessions: int = 1000,
    snapshots_path: Optional[Union[str, Path]] = None,
    auto_port: bool = True,
) -> Optional[DevToolsBundle]:
    """
    One-line setup for aiogram-fsm-inspector.
    Wraps FSM storage, registers outer middleware, introspects StatesGroups,
    and binds the Uvicorn ASGI server to Dispatcher startup/shutdown lifecycle.
    """
    if not enabled:
        logger.info("aiogram-devtools is disabled.")
        return None

    event_bus = EventBus()

    # 1. Dual replacement of FSM storage (Rule 2)
    original_storage = dp.fsm.storage
    if isinstance(original_storage, DevToolsStorageProxy):
        storage_proxy = original_storage
    else:
        storage_proxy = DevToolsStorageProxy(
            storage=original_storage,
            bus=event_bus,
            max_history_per_user=max_history_per_user,
            max_sessions=max_sessions,
        )
        dp.fsm.storage = storage_proxy
        try:
            dp.storage = storage_proxy
        except AttributeError:
            # In aiogram 3.x, dp.storage is a read-only property returning dp.fsm.storage
            pass

    # 2. Outer middleware for metadata and execution timing (Rule 1)
    middleware = DevToolsMiddleware(bus=event_bus, max_users=max_sessions * 2)
    dp.update.outer_middleware(middleware)

    # 3. State scanner
    state_registry = StateRegistry()
    state_registry.scan()

    # 4. Snapshots & Presets
    snapshot_manager = SnapshotManager(filepath=snapshots_path)

    # 5. WebSocket & Auth
    ws_hub = WebSocketHub()
    auth_validator = TokenAuthValidator(required_token=auth_token)

    # 6. FastAPI ASGI App
    app = create_devtools_app(
        storage_proxy=storage_proxy,
        event_bus=event_bus,
        middleware=middleware,
        state_registry=state_registry,
        snapshot_manager=snapshot_manager,
        ws_hub=ws_hub,
        auth_validator=auth_validator,
    )

    # 7. Redis cold-start auto-discovery hook if storage is Redis
    _setup_redis_cold_start_if_applicable(dp, original_storage, storage_proxy)

    # 8. Server Lifecycle (Rule 4)
    server_manager = DevToolsServerManager(
        app=app,
        host=host,
        port=port,
        log_level=log_level,
        auth_token=auth_token,
        ws_hub=ws_hub,
        auto_port=auto_port,
    )
    server_manager.attach_to_dispatcher(dp)

    logger.info("aiogram-fsm-inspector configured. Web UI available at http://%s:%d", host, server_manager.port)

    return DevToolsBundle(
        app=app,
        storage_proxy=storage_proxy,
        event_bus=event_bus,
        middleware=middleware,
        state_registry=state_registry,
        snapshot_manager=snapshot_manager,
        server_manager=server_manager,
        ws_hub=ws_hub,
    )


def _setup_redis_cold_start_if_applicable(
    dp: Dispatcher,
    storage: Any,
    proxy: DevToolsStorageProxy,
) -> None:
    """If RedisStorage is used, discover existing active sessions on startup."""
    # Check if storage has redis attribute or is RedisStorage
    if not hasattr(storage, "redis"):
        return

    @dp.startup()
    async def _scan_redis_sessions(bot: Optional[Bot] = None, *args, **kwargs) -> None:
        try:
            from .serialization import dict_to_storage_key
            from aiogram.fsm.storage.base import StorageKey

            redis = storage.redis
            key_builder = getattr(storage, "key_builder", None)
            prefix = getattr(key_builder, "prefix", "fsm") if key_builder else "fsm"
            default_bot_id = bot.id if bot else 0

            count = 0
            async for raw_key in redis.scan_iter(match=f"{prefix}:*", count=100):
                key_str = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else str(raw_key)
                parts = key_str.split(":")
                if len(parts) >= 3 and parts[-1] in ("state", "data"):
                    try:
                        # Extract core segments between prefix and state/data
                        core = parts[1:-1]
                        integers = [int(p) for p in core if p.lstrip("-").isdigit()]
                        if len(integers) < 2:
                            continue

                        # Default heuristic: if 2 integers -> chat_id, user_id
                        # If 3 integers and first matches default_bot_id -> bot_id, chat_id, user_id
                        if len(integers) == 2:
                            bot_id = default_bot_id
                            chat_id = integers[0]
                            user_id = integers[1]
                        else:
                            bot_id = integers[0]
                            chat_id = integers[1]
                            user_id = integers[2]

                        destiny = "default"
                        for p in core:
                            if not p.lstrip("-").isdigit() and p not in ("fsm", "state", "data"):
                                destiny = p
                                break

                        skey = StorageKey(
                            bot_id=bot_id,
                            chat_id=chat_id,
                            user_id=user_id,
                            destiny=destiny,
                        )
                        proxy.register_key(skey)
                        count += 1
                    except Exception:
                        continue
            logger.info("Discovered %d active FSM sessions from Redis on startup.", count)
        except Exception as exc:
            logger.warning("Redis cold-start session discovery encountered an error: %s", exc)


# Alias
setup_inspector = setup_devtools
