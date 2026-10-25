"""
aiogram-fsm-inspector (aiogram-devtools)
In-Process real-time FSM debugging and inspection suite for aiogram 3.x.
"""

from .event_bus import EventBus
from .middleware import DevToolsMiddleware
from .scanner import StateRegistry
from .serialization import merge_memory_data, safe_json_dump_ready
from .setup import DevToolsBundle, setup_devtools, setup_inspector
from .snapshots import SnapshotManager
from .storage import DevToolsStorageProxy

__version__ = "0.1.0"
__all__ = [
    "setup_devtools",
    "setup_inspector",
    "DevToolsBundle",
    "DevToolsStorageProxy",
    "DevToolsMiddleware",
    "StateRegistry",
    "EventBus",
    "SnapshotManager",
    "safe_json_dump_ready",
    "merge_memory_data",
]
