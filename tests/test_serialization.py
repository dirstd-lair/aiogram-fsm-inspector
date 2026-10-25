from __future__ import annotations

import dataclasses
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from aiogram.fsm.storage.base import StorageKey
from pydantic import BaseModel

from aiogram_fsm_inspector.serialization import (
    dict_to_storage_key,
    merge_memory_data,
    safe_json_dump_ready,
    storage_key_to_dict,
)


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"


@dataclasses.dataclass
class OrderItem:
    item_id: int
    name: str
    price: Decimal


class ProfileModel(BaseModel):
    bio: str
    level: int


class CustomPythonObject:
    def __init__(self, val: str):
        self.val = val

    def __repr__(self):
        return f"CustomPythonObject('{self.val}')"


def test_serialization_primitives():
    assert safe_json_dump_ready(None) is None
    assert safe_json_dump_ready(123) == 123
    assert safe_json_dump_ready("hello") == "hello"
    assert safe_json_dump_ready(True) is True
    assert safe_json_dump_ready([1, 2, "3"]) == [1, 2, "3"]


def test_serialization_dates_and_decimals():
    now = datetime(2026, 10, 25, 12, 0, 0)
    d = safe_json_dump_ready(now)
    assert d["__devtools_type__"] == "datetime"
    assert d["__devtools_val__"] == "2026-10-25T12:00:00"

    today = date(2026, 10, 25)
    d_today = safe_json_dump_ready(today)
    assert d_today["__devtools_type__"] == "date"
    assert d_today["__devtools_val__"] == "2026-10-25"

    dec = Decimal("4500.50")
    d_dec = safe_json_dump_ready(dec)
    assert d_dec["__devtools_type__"] == "Decimal"
    assert d_dec["__devtools_val__"] == "4500.50"


def test_serialization_dataclass_and_pydantic():
    order = OrderItem(item_id=1, name="Widget", price=Decimal("19.99"))
    d_order = safe_json_dump_ready(order)
    assert "dataclass(OrderItem)" in d_order["__devtools_type__"]
    assert d_order["__devtools_val__"]["name"] == "Widget"

    profile = ProfileModel(bio="Telegram dev", level=5)
    d_profile = safe_json_dump_ready(profile)
    assert "Pydantic" in d_profile["__devtools_type__"]
    assert d_profile["__devtools_val__"]["bio"] == "Telegram dev"


def test_serialization_readonly_custom_object():
    obj = CustomPythonObject("secret_state")
    d_obj = safe_json_dump_ready(obj)
    assert d_obj.get("__readonly__") is True
    assert "CustomPythonObject" in d_obj["__devtools_type__"]


def test_merge_memory_data_preserves_readonly():
    obj = CustomPythonObject("original_value")
    original = {
        "complex_obj": obj,
        "counter": 10,
    }
    incoming = {
        "complex_obj": {
            "__devtools_val__": repr(obj),
            "__devtools_type__": "object(CustomPythonObject)",
            "__readonly__": True,
        },
        "counter": 11,
    }
    merged = merge_memory_data(original, incoming)
    # The original instance was preserved untouched
    assert merged["complex_obj"] is obj
    assert merged["counter"] == 11


def test_storage_key_conversions():
    key = StorageKey(
        bot_id=111,
        chat_id=222,
        user_id=333,
        thread_id=444,
        destiny="custom",
    )
    d = storage_key_to_dict(key)
    assert d["bot_id"] == 111
    assert d["chat_id"] == 222
    assert d["user_id"] == 333
    assert d["thread_id"] == 444
    assert d["destiny"] == "custom"

    reconstructed = dict_to_storage_key(d)
    assert reconstructed.bot_id == key.bot_id
    assert reconstructed.chat_id == key.chat_id
    assert reconstructed.user_id == key.user_id
    assert reconstructed.thread_id == key.thread_id
    assert reconstructed.destiny == key.destiny


def test_merge_memory_data_preserves_sets_and_tuples():
    original = {
        "tags": {"python", "asyncio"},
        "coords": (10, 20),
        "name": "tester",
    }
    incoming = {
        "tags": ["python", "asyncio", "aiogram"],  # UI sent back as list
        "coords": [10, 30],                         # UI sent back as list
        "name": "tester_updated",
    }
    merged = merge_memory_data(original, incoming)
    assert isinstance(merged["tags"], set)
    assert merged["tags"] == {"python", "asyncio", "aiogram"}
    assert isinstance(merged["coords"], tuple)
    assert merged["coords"] == (10, 30)
    assert merged["name"] == "tester_updated"
