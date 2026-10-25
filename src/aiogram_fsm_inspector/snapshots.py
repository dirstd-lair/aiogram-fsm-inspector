from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .serialization import safe_json_dump_ready

if TYPE_CHECKING:
    from aiogram.fsm.storage.base import StorageKey
    from .storage import DevToolsStorageProxy

logger = logging.getLogger("aiogram_fsm_inspector.snapshots")


class SnapshotManager:
    """
    Manages persistent state presets (bookmarks) saved to a local JSON file.
    Enables developers to save complex multi-step state/data scenarios
    and apply them instantly to any active user session.
    """

    DEFAULT_FILENAME = ".aiogram_devtools_snapshots.json"

    def __init__(self, filepath: Optional[Union[str, Path]] = None) -> None:
        self.filepath = Path(filepath or self.DEFAULT_FILENAME)
        self._presets: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.filepath.exists():
            self._presets = {}
            return
        try:
            content = self.filepath.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                self._presets = data
            elif isinstance(data, list):
                self._presets = {p["id"]: p for p in data if "id" in p}
        except Exception as exc:
            logger.warning("Failed to load snapshots file %s: %s", self.filepath, exc)
            self._presets = {}

    def _save(self) -> None:
        try:
            temp_file = self.filepath.with_suffix(".tmp")
            temp_file.write_text(
                json.dumps(self._presets, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            # Atomic rename / replace
            temp_file.replace(self.filepath)
        except Exception as exc:
            logger.error("Failed saving snapshots to %s: %s", self.filepath, exc)

    def list_presets(self) -> List[Dict[str, Any]]:
        """Returns list of all saved presets sorted by creation date."""
        return sorted(
            self._presets.values(),
            key=lambda x: x.get("created_at", 0),
            reverse=True,
        )

    def get_preset(self, preset_id: str) -> Optional[Dict[str, Any]]:
        return self._presets.get(preset_id)

    def save_preset(
        self,
        name: str,
        state: Optional[str],
        data: Dict[str, Any],
        description: str = "",
    ) -> Dict[str, Any]:
        preset_id = str(uuid.uuid4())[:8]
        preset = {
            "id": preset_id,
            "name": name,
            "description": description,
            "state": state,
            "data": safe_json_dump_ready(data),
            "created_at": time.time(),
        }
        self._presets[preset_id] = preset
        self._save()
        logger.info("Saved state preset '%s' (id: %s)", name, preset_id)
        return preset

    # Alias for convenience
    create_preset = save_preset

    def delete_preset(self, preset_id: str) -> bool:
        if preset_id in self._presets:
            del self._presets[preset_id]
            self._save()
            logger.info("Deleted preset id: %s", preset_id)
            return True
        return False

    async def apply_preset(
        self,
        preset_id: str,
        key: StorageKey,
        storage_proxy: DevToolsStorageProxy,
    ) -> Optional[Dict[str, Any]]:
        preset = self.get_preset(preset_id)
        if not preset:
            return None

        state = preset.get("state")
        data = preset.get("data", {})

        await storage_proxy.set_state(key=key, state=state, source="preset_applied")
        await storage_proxy.set_data(key=key, data=data, source="preset_applied")

        logger.info("Applied preset '%s' to session key %s", preset.get("name"), key)
        return preset
