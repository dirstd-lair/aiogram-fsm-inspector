from __future__ import annotations

import asyncio
import collections
import copy
import logging
import time
from typing import Any, Deque, Dict, List, Optional, Set, OrderedDict

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey

from .event_bus import EventBus
from .serialization import (
    merge_memory_data,
    safe_json_dump_ready,
    storage_key_to_dict,
)

logger = logging.getLogger("aiogram_fsm_inspector.storage")


class DevToolsStorageProxy(BaseStorage):
    """
    Transparent proxy wrapping any aiogram 3.x BaseStorage implementation.
    Tracks active StorageKeys, intercepts all state/data mutations, maintains
    a Time-Travel history ring buffer, and publishes real-time events to EventBus.
    """

    def __init__(
        self,
        storage: BaseStorage,
        bus: EventBus,
        max_history_per_user: int = 20,
        max_sessions: int = 1000,
    ) -> None:
        self._storage = storage
        self._bus = bus
        self._max_history = max_history_per_user
        self._max_sessions = max_sessions
        # Bounded LRU OrderedDict: StorageKey -> last_access_timestamp
        self._known_keys: OrderedDict[StorageKey, float] = collections.OrderedDict()
        # In-memory history ring-buffer: StorageKey -> Deque[Snapshot]
        self._history: Dict[StorageKey, Deque[Dict[str, Any]]] = collections.defaultdict(
            lambda: collections.deque(maxlen=self._max_history)
        )
        # In-memory cache of non-JSON objects for MemoryStorage to prevent destructive wipes
        self._raw_data_cache: Dict[StorageKey, Dict[str, Any]] = collections.defaultdict(dict)
        # Concurrency locks per StorageKey to avoid race conditions during UI updates
        self._key_locks: Dict[StorageKey, asyncio.Lock] = collections.defaultdict(asyncio.Lock)

    @property
    def unwrapped_storage(self) -> BaseStorage:
        """Returns the underlying BaseStorage instance."""
        return self._storage

    @property
    def known_keys(self) -> Set[StorageKey]:
        """Returns a snapshot of all discovered StorageKeys."""
        return set(self._known_keys.keys())

    def register_key(self, key: StorageKey) -> None:
        """Adds a key to the index of known active sessions with LRU eviction."""
        self._known_keys[key] = time.time()
        self._known_keys.move_to_end(key)
        while len(self._known_keys) > self._max_sessions:
            evicted_key, _ = self._known_keys.popitem(last=False)
            self._history.pop(evicted_key, None)
            self._raw_data_cache.pop(evicted_key, None)
            self._key_locks.pop(evicted_key, None)

    def unregister_key(self, key: StorageKey) -> None:
        """Removes a key from known active sessions."""
        self._known_keys.pop(key, None)
        self._history.pop(key, None)
        self._raw_data_cache.pop(key, None)
        self._key_locks.pop(key, None)

    async def _record_snapshot(
        self,
        key: StorageKey,
        trigger: str,
        state: Optional[str],
        data: Dict[str, Any],
    ) -> None:
        """Appends a state snapshot into the session's time-travel ring buffer."""
        snapshot = {
            "timestamp": time.time(),
            "trigger": trigger,
            "state": state,
            "data": copy.deepcopy(data),
        }
        self._history[key].append(snapshot)

    def get_history(self, key: StorageKey) -> List[Dict[str, Any]]:
        """Returns chronological list of state snapshots for given key."""
        hist = self._history.get(key)
        if not hist:
            return []
        return [
            {
                "timestamp": item["timestamp"],
                "trigger": item["trigger"],
                "state": item["state"],
                "data": safe_json_dump_ready(item["data"]),
            }
            for item in hist
        ]

    async def set_state(
        self,
        key: StorageKey,
        state: StateType = None,
        source: str = "telegram",
    ) -> None:
        self.register_key(key)
        await self._storage.set_state(key=key, state=state)
        resolved_state = state.state if isinstance(state, State) else state

        # Read current data to preserve full snapshot
        current_data = await self.get_data(key=key)
        await self._record_snapshot(key, trigger=source, state=resolved_state, data=current_data)

        await self._bus.publish(
            "STATE_UPDATED",
            {
                "key": storage_key_to_dict(key),
                "state": resolved_state,
                "source": source,
                "timestamp": time.time(),
            },
        )

    async def get_state(self, key: StorageKey) -> Optional[str]:
        self.register_key(key)
        return await self._storage.get_state(key=key)

    async def set_data(
        self,
        key: StorageKey,
        data: Dict[str, Any],
        source: str = "telegram",
    ) -> None:
        self.register_key(key)
        self._raw_data_cache[key] = copy.deepcopy(data)
        await self._storage.set_data(key=key, data=data)

        current_state = await self._storage.get_state(key=key)
        await self._record_snapshot(key, trigger=source, state=current_state, data=data)

        safe_data = safe_json_dump_ready(data)
        await self._bus.publish(
            "DATA_UPDATED",
            {
                "key": storage_key_to_dict(key),
                "data": safe_data,
                "source": source,
                "timestamp": time.time(),
            },
        )

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        self.register_key(key)
        data = await self._storage.get_data(key=key)
        if data:
            self._raw_data_cache[key] = data
        return data

    async def update_data(
        self,
        key: StorageKey,
        data: Dict[str, Any],
        source: str = "telegram",
    ) -> Dict[str, Any]:
        """
        Explicitly overridden to guarantee event publishing even if underlying storage
        does not invoke self.set_data().
        """
        self.register_key(key)
        updated_data = await self._storage.update_data(key=key, data=data)
        self._raw_data_cache[key] = copy.deepcopy(updated_data)

        current_state = await self._storage.get_state(key=key)
        await self._record_snapshot(key, trigger=source, state=current_state, data=updated_data)

        safe_data = safe_json_dump_ready(updated_data)
        await self._bus.publish(
            "DATA_UPDATED",
            {
                "key": storage_key_to_dict(key),
                "data": safe_data,
                "source": source,
                "timestamp": time.time(),
            },
        )
        return updated_data

    async def clear_session(self, key: StorageKey) -> None:
        """Completely clears state and data for the key."""
        await self._storage.set_state(key=key, state=None)
        await self._storage.set_data(key=key, data={})
        self._raw_data_cache.pop(key, None)

        await self._record_snapshot(key, trigger="clear", state=None, data={})
        await self._bus.publish(
            "STATE_UPDATED",
            {
                "key": storage_key_to_dict(key),
                "state": None,
                "source": "clear",
                "timestamp": time.time(),
            },
        )
        await self._bus.publish(
            "DATA_UPDATED",
            {
                "key": storage_key_to_dict(key),
                "data": {},
                "source": "clear",
                "timestamp": time.time(),
            },
        )

    async def rollback(self, key: StorageKey) -> Optional[Dict[str, Any]]:
        """
        Time-travel rollback: restores the previous snapshot from history ring-buffer,
        reverting both FSM state and data to before the last user interaction.
        Returns the restored snapshot or None if history is insufficient.
        """
        hist = self._history.get(key)
        if not hist or len(hist) < 2:
            logger.info("Rollback requested for %s, but history depth < 2", key)
            return None

        current = hist[-1]
        current_state = current["state"]
        current_data = current["data"]

        # Pop current snapshot
        hist.pop()

        # If state was changed in this interaction, pop back to previous state
        if current_state is not None:
            while hist and hist[-1]["state"] == current_state:
                hist.pop()
        else:
            while hist and hist[-1]["data"] == current_data:
                hist.pop()

        if not hist:
            return None

        # Peek at target snapshot
        target = copy.deepcopy(hist[-1])

        target_state = target["state"]
        target_data = target["data"]

        # Apply to storage
        await self._storage.set_state(key=key, state=target_state)
        await self._storage.set_data(key=key, data=target_data)
        self._raw_data_cache[key] = copy.deepcopy(target_data)

        # Notify via bus
        await self._bus.publish(
            "STATE_UPDATED",
            {
                "key": storage_key_to_dict(key),
                "state": target_state,
                "source": "rollback",
                "timestamp": time.time(),
            },
        )
        await self._bus.publish(
            "DATA_UPDATED",
            {
                "key": storage_key_to_dict(key),
                "data": safe_json_dump_ready(target_data),
                "source": "rollback",
                "timestamp": time.time(),
            },
        )

        return {
            "state": target_state,
            "data": safe_json_dump_ready(target_data),
            "timestamp": target["timestamp"],
        }

    async def merge_data_from_ui(self, key: StorageKey, incoming_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Applies UI edits while protecting non-serializable objects from erasure.
        Guarded with an asyncio.Lock per key to avoid race conditions.
        """
        async with self._key_locks[key]:
            current_data = await self.get_data(key=key)
            merged = merge_memory_data(current_data, incoming_json)
            await self.set_data(key=key, data=merged, source="devtools_ui")
            return merged

    async def close(self) -> None:
        """Closes the underlying storage."""
        await self._storage.close()
