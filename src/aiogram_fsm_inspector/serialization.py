from __future__ import annotations

import base64
import dataclasses
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional, Union
from uuid import UUID

from aiogram.fsm.storage.base import StorageKey


def safe_json_dump_ready(obj: Any) -> Any:
    """
    Recursively transforms arbitrary Python data structures into JSON-serializable types.
    Enriches custom objects with devtools metadata to prevent type erasure in UI.
    """
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj

    if isinstance(obj, (datetime, date)):
        return {
            "__devtools_val__": obj.isoformat(),
            "__devtools_type__": "datetime" if isinstance(obj, datetime) else "date",
        }

    if isinstance(obj, time):
        return {
            "__devtools_val__": obj.isoformat(),
            "__devtools_type__": "time",
        }

    if isinstance(obj, timedelta):
        return {
            "__devtools_val__": str(obj),
            "__devtools_type__": "timedelta",
            "total_seconds": obj.total_seconds(),
        }

    if isinstance(obj, Decimal):
        return {
            "__devtools_val__": str(obj),
            "__devtools_type__": "Decimal",
        }

    if isinstance(obj, UUID):
        return {
            "__devtools_val__": str(obj),
            "__devtools_type__": "UUID",
        }

    if isinstance(obj, bytes):
        return {
            "__devtools_val__": base64.b64encode(obj).decode("ascii"),
            "__devtools_type__": "bytes(base64)",
        }

    if isinstance(obj, Enum):
        return {
            "__devtools_val__": safe_json_dump_ready(obj.value),
            "__devtools_type__": f"Enum({obj.__class__.__name__})",
        }

    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        fields_dict = dataclasses.asdict(obj)
        return {
            "__devtools_val__": safe_json_dump_ready(fields_dict),
            "__devtools_type__": f"dataclass({obj.__class__.__name__})",
        }

    # Pydantic v2
    if hasattr(obj, "model_dump") and callable(obj.model_dump):
        try:
            return {
                "__devtools_val__": safe_json_dump_ready(obj.model_dump()),
                "__devtools_type__": f"Pydantic({obj.__class__.__name__})",
            }
        except Exception:
            pass

    # Pydantic v1
    if hasattr(obj, "dict") and callable(obj.dict):
        try:
            return {
                "__devtools_val__": safe_json_dump_ready(obj.dict()),
                "__devtools_type__": f"Pydantic({obj.__class__.__name__})",
            }
        except Exception:
            pass

    if isinstance(obj, (list, tuple, set, frozenset)):
        return [safe_json_dump_ready(item) for item in obj]

    if isinstance(obj, dict):
        return {str(k): safe_json_dump_ready(v) for k, v in obj.items()}

    # Fallback for arbitrary Python classes (Read-Only Representation)
    return {
        "__devtools_val__": repr(obj),
        "__devtools_type__": f"object({obj.__class__.__name__})",
        "__readonly__": True,
    }


def merge_memory_data(original: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safely merges incoming JSON from web UI into original in-memory data dict.
    Preserves original complex Python instances if their representation was unchanged or marked read-only.
    """
    merged = dict(original)
    for key, val in incoming.items():
        if isinstance(val, dict):
            # If incoming field has readonly tag and existed previously, preserve untouched
            if val.get("__readonly__") and key in original:
                continue

            # If incoming field is an unwrap candidate
            if "__devtools_val__" in val:
                devtools_type = val.get("__devtools_type__", "")
                devtools_val = val["__devtools_val__"]

                # If original value exists and representation didn't change, keep original
                if key in original:
                    curr_val = original[key]
                    if safe_json_dump_ready(curr_val) == val:
                        continue

                # Otherwise assign unwrapped value
                if devtools_type == "Decimal":
                    try:
                        merged[key] = Decimal(str(devtools_val))
                        continue
                    except Exception:
                        pass
                elif devtools_type == "datetime":
                    try:
                        merged[key] = datetime.fromisoformat(devtools_val)
                        continue
                    except Exception:
                        pass
                elif devtools_type == "date":
                    try:
                        merged[key] = date.fromisoformat(devtools_val)
                        continue
                    except Exception:
                        pass
                elif devtools_type == "UUID":
                    try:
                        merged[key] = UUID(str(devtools_val))
                        continue
                    except Exception:
                        pass

                merged[key] = devtools_val
                continue

        # Preserve collection types if original was set/tuple/frozenset
        if key in original:
            curr_val = original[key]
            if isinstance(curr_val, set) and isinstance(val, list):
                merged[key] = set(val)
                continue
            if isinstance(curr_val, frozenset) and isinstance(val, list):
                merged[key] = frozenset(val)
                continue
            if isinstance(curr_val, tuple) and isinstance(val, list):
                merged[key] = tuple(val)
                continue

        merged[key] = val

    # Remove deleted keys
    for k in list(merged.keys()):
        if k not in incoming:
            del merged[k]

    return merged


def storage_key_to_dict(key: StorageKey) -> Dict[str, Any]:
    """Converts a StorageKey dataclass into a clean dictionary."""
    return {
        "bot_id": key.bot_id,
        "chat_id": key.chat_id,
        "user_id": key.user_id,
        "thread_id": key.thread_id,
        "business_connection_id": getattr(key, "business_connection_id", None),
        "destiny": key.destiny,
    }


def dict_to_storage_key(d: Dict[str, Any]) -> StorageKey:
    """Reconstructs a StorageKey dataclass from a dictionary."""
    bot_id = int(d.get("bot_id", 0))
    chat_id = int(d.get("chat_id", 0))
    user_id = int(d.get("user_id", 0))
    thread_id = int(d["thread_id"]) if d.get("thread_id") is not None else None
    business_connection_id = d.get("business_connection_id")
    destiny = str(d.get("destiny", "default"))

    # Support aiogram versions with or without business_connection_id
    try:
        return StorageKey(
            bot_id=bot_id,
            chat_id=chat_id,
            user_id=user_id,
            thread_id=thread_id,
            business_connection_id=business_connection_id,
            destiny=destiny,
        )
    except TypeError:
        # Fallback if aiogram version does not support business_connection_id
        return StorageKey(
            bot_id=bot_id,
            chat_id=chat_id,
            user_id=user_id,
            thread_id=thread_id,
            destiny=destiny,
        )
