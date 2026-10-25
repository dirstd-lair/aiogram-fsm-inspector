"""
Multi-Bot Runner for aiogram-fsm-inspector.
Runs all three demo bots concurrently:
1. Online Salon / Cart Bot (@online_salon_demo_bot) -> http://127.0.0.1:8080
2. Quiz & Vocab Bot (@learning_words_ai_bot)         -> http://127.0.0.1:8081
3. IT Support Bot (@chgpgt_ru_bot)                   -> http://127.0.0.1:8082
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

EXAMPLES_DIR = Path(__file__).parent
BOT_SCRIPTS = [
    ("Salon Bot (:8080)", EXAMPLES_DIR / "simple_bot.py"),
    ("Quiz Bot (:8081)", EXAMPLES_DIR / "quiz_bot.py"),
    ("Support Bot (:8082)", EXAMPLES_DIR / "support_bot.py"),
]


def load_env_file_if_present() -> None:
    """Lightweight .env parser for standalone example execution."""
    env_file = EXAMPLES_DIR.parent / ".env"
    if not env_file.exists():
        return
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


async def stream_output(prefix: str, stream: asyncio.StreamReader) -> None:
    while True:
        line = await stream.readline()
        if not line:
            break
        decoded = line.decode("utf-8", errors="replace").rstrip()
        if decoded:
            print(f"[{prefix}] {decoded}")


async def run_bot_process(name: str, script_path: Path) -> asyncio.subprocess.Process:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(script_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    if proc.stdout:
        asyncio.create_task(stream_output(name, proc.stdout))
    return proc


async def main() -> None:
    load_env_file_if_present()
    print("\n" + "═" * 70)
    print(" 🚀 Launching 3 Bots with aiogram-fsm-inspector Multi-Bot Hub...")
    print("═" * 70)

    processes: list[asyncio.subprocess.Process] = []

    for name, script in BOT_SCRIPTS:
        print(f"  -> Starting {name} ({script.name})...")
        proc = await run_bot_process(name, script)
        processes.append(proc)
        # Small delay between boots to ensure sequential port binding
        await asyncio.sleep(1.2)

    print("\n" + "═" * 70)
    print("  ⭐ Open the Unified Dashboard: http://127.0.0.1:8080")
    print("  Use the 'Select Bot' dropdown in the top bar or 'All Bots' mode!")
    print("  Press Ctrl+C to terminate all bots gracefully.")
    print("═" * 70 + "\n")

    try:
        await asyncio.gather(*(p.wait() for p in processes))
    except (asyncio.CancelledError, KeyboardInterrupt):
        print("\n[Shutdown] Stopping all bots...")
        for p in processes:
            try:
                p.terminate()
            except Exception:
                pass
        await asyncio.gather(*(p.wait() for p in processes), return_exceptions=True)
        print("[Shutdown] All bots stopped cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
