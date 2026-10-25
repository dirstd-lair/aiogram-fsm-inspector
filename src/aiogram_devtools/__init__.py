"""
aiogram_devtools alias for aiogram_fsm_inspector.
Provides identical API for backwards compatibility and ease of use.
"""

from aiogram_fsm_inspector import (
    DevToolsBundle,
    DevToolsMiddleware,
    DevToolsStorageProxy,
    EventBus,
    SnapshotManager,
    StateRegistry,
    merge_memory_data,
    safe_json_dump_ready,
    setup_devtools,
    setup_inspector,
)

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
