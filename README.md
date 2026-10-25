# aiogram-fsm-inspector (`aiogram-devtools`)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![aiogram 3.x](https://img.shields.io/badge/aiogram-3.x-green.svg)](https://github.com/aiogram/aiogram)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-teal.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**`aiogram-fsm-inspector`** is an in-process real-time debugging suite and web dashboard for Telegram bots powered by **aiogram 3.x** (`aiogram >= 3.10`).

It launches an embedded FastAPI ASGI server inside the **identical asyncio event loop** running your bot, intercepts state transitions via a transparent `BaseStorage` proxy, and serves a reactive single-file SPA web dashboard with zero Node.js/npm dependencies.

---

## ⚡ Features

- **One-Line Integration:** Add `setup_devtools(dp)` to your bot, and the web panel is instantly available.
- **In-Process ASGI Sidecar:** Uvicorn runs directly inside the bot's event loop via `@dp.startup()` and `@dp.shutdown()`, sharing memory directly with `MemoryStorage` and `RedisStorage`.
- **Live User Inspector:** Monitor active user sessions in real time via WebSockets. Visual pulse indicator highlights when a user triggers a Telegram update.
- **State Jumper (Autocomplete):** Dynamically reflects all `StatesGroup` subclasses declared in your Python runtime. Switch a user to any step with one click.
- **Interactive JSON Data Editor:** Hot-edit `FSMContext` data dictionary with real-time JSON validation, key/byte counters, and `Ctrl+S` / `Cmd+S` keyboard shortcuts.
- **Safe Object Serialization:** Handles `datetime`, `Decimal`, `UUID`, `Enum`, `dataclass`, and `Pydantic` models without crashing with `TypeError`. Unchanged complex objects in memory are protected from destructive overwrites.
- **Multi-Bot Unified Hub:** Auto-discovers and connects multiple bot processes across ports `8080..8086`. Switch between bots in the header or monitor all bots simultaneously in a consolidated view.
- **Auto-Port Fallback:** If port `8080` is busy, the inspector automatically binds to the next free port (`8081`, `8082`, etc.) without crashing.
- **Bilingual Interface:** One-click toggle between English and Russian with full localization.
- **State Presets & Bookmarks:** Save complex multi-step state and data combinations to local JSON bookmarks (`.aiogram_devtools_snapshots.json`) and apply them to any user session in one click.
- **Time-Travel Rollback:** Step backwards through recent state and data snapshots before a user interaction occurred.
- **Redis Cold-Start Discovery:** Discovers existing sessions non-blockingly via `redis.scan_iter(match="fsm:*")` instead of blocking `KEYS *`.
- **Zero-Build Web UI:** Pre-built responsive dark/light SPA styled with Tailwind CSS, embedded directly inside Python package data.

---

## 📦 Installation

```bash
pip install aiogram-fsm-inspector
```

Or using `uv`:

```bash
uv add aiogram-fsm-inspector
```

---

## 🚀 Quickstart

Connect the inspector in **one line of code** inside your bot's entry point:

```python
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram_fsm_inspector import setup_devtools  # or: from aiogram_devtools import setup_devtools

bot = Bot(token="YOUR_TELEGRAM_BOT_TOKEN")
dp = Dispatcher(storage=MemoryStorage())

# Connect inspector on http://127.0.0.1:8080
setup_devtools(dp, host="127.0.0.1", port=8080)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

Open your browser at **[http://127.0.0.1:8080](http://127.0.0.1:8080)** to view the live dashboard.

---

## 🛡️ Production Guard & Security

1. **Loopback by Default:** The inspector binds exclusively to `127.0.0.1`, blocking access from external network interfaces.
2. **Public Binding Protection:** If configured to bind to `0.0.0.0` or a public interface, an `auth_token` is strictly required:
   ```python
   setup_devtools(dp, host="0.0.0.0", port=8080, auth_token="super_secret_token")
   ```
   Or explicitly allow unsafe local container access via environment variable:
   ```bash
   export AIOGRAM_DEVTOOLS_UNSAFE=1
   ```
3. **Authentication:** Pass the token via:
   - Header: `Authorization: Bearer <auth_token>`
   - Query param: `http://localhost:8080/?token=<auth_token>`

---

## 🔌 REST & WebSocket API Reference

The embedded FastAPI app provides endpoints at `/api/v1`:

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/info` | Inspector metadata, port, bot username, and active session count |
| `GET` | `/api/v1/sessions` | List all discovered active sessions |
| `GET` | `/api/v1/sessions/{chat_id}/{user_id}` | Fetch detailed session state, data, and history |
| `PATCH` | `/api/v1/sessions/{chat_id}/{user_id}/state` | Force change user FSM step (`{"state": "Group:step"}`) |
| `PUT` | `/api/v1/sessions/{chat_id}/{user_id}/data` | Hot-edit user FSM data dictionary |
| `POST` | `/api/v1/sessions/{chat_id}/{user_id}/clear` | Clear state and data for session |
| `POST` | `/api/v1/sessions/{chat_id}/{user_id}/rollback` | Rollback session to previous snapshot |
| `GET` | `/api/v1/states-tree` | Get reflected `StatesGroup` class tree |
| `GET` | `/api/v1/snapshots` | List saved state presets |
| `POST` | `/api/v1/snapshots` | Save new state preset |
| `POST` | `/api/v1/snapshots/{id}/apply` | Apply preset to a session |
| `DELETE` | `/api/v1/snapshots/{id}` | Delete preset |
| `WS` | `/api/v1/ws` | Real-time WebSocket pub/sub |

---

## 📄 License

MIT License. Designed with precision for the aiogram ecosystem.
