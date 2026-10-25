# CLAUDE.md: aiogram-devtools / aiogram-fsm-inspector

## Overview
`aiogram-fsm-inspector` (SDK + embedded web panel) is an in-process real-time FSM debugging and inspection suite for Telegram bots built on **aiogram 3.x** (`aiogram >= 3.10`).

## Specialized Skills Reference
Before modifying or implementing any modules, review the specialized skill rules in `.agents/skills/`:
- [`01-aiogram3-fsm-internals.md`](.agents/skills/01-aiogram3-fsm-internals.md): aiogram 3.x `StorageKey`, `DevToolsStorageProxy`, `dp.fsm.storage` dual replacement, `update_data` interception, and recursive `StatesGroup` scanning.
- [`02-uvicorn-in-process-sidecar.md`](.agents/skills/02-uvicorn-in-process-sidecar.md): In-Process ASGI Sidecar pattern, `EmbeddedUvicornServer` without OS signal interception, dispatcher lifecycle hooks, and safe WebSocket pooling.
- [`03-redis-and-memory-introspection.md`](.agents/skills/03-redis-and-memory-introspection.md): Non-blocking Redis `SCAN` cold-start discovery, `DefaultKeyBuilder` reverse parsing, and safe recursive serialization of non-JSON Python objects (`datetime`, `Decimal`, `Pydantic`).
- [`04-zero-build-frontend.md`](.agents/skills/04-zero-build-frontend.md): Zero-build single-file reactive SPA (Tailwind + Alpine/Vanilla), WebSocket live updates, state jumper, interactive JSON editor with `Ctrl+S`, presets, and time-travel rollback.

---

## Non-Negotiable Architecture Constraints

1. **aiogram 3.x Exclusivity:**
   - NEVER use aiogram 2.x legacy: `Bot.get_current()`, `Dispatcher.get_current()`, `executor.start_polling()`, `register_message_handler()`.
   - All storage calls take `StorageKey(bot_id=..., chat_id=..., user_id=..., ...)`.

2. **Dual Storage Replacement:**
   - In `setup_devtools(dp)`, always replace BOTH:
     `dp.fsm.storage = proxy` and `dp.storage = proxy`.

3. **Explicit `update_data` Override:**
   - `DevToolsStorageProxy` must override `update_data` and emit `DATA_UPDATED`. Do not rely on `set_data` being called by underlying storages.

4. **Uvicorn Inside Event Loop:**
   - NEVER call `uvicorn.run()`! Run `server.serve()` as an `asyncio.Task` inside `@dp.startup()`.
   - Override `install_signal_handlers()` to `pass` so aiogram keeps control of `SIGINT`/`SIGTERM`.

5. **Redis Inspection:**
   - NEVER call `KEYS *`! Use `async for raw_key in redis.scan_iter(...)`.

6. **Object Serialization:**
   - Never pass raw dictionaries containing `datetime`, `Decimal`, or `Pydantic` models to standard `json.dumps()` or `JSONResponse`. Always pass through `safe_json_dump_ready()`.

7. **Zero-Build UI:**
   - The frontend is pre-built, single-file HTML/CSS/JS without requiring Node.js at runtime.
