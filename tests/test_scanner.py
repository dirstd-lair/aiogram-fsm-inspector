from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup

from aiogram_fsm_inspector.scanner import StateRegistry


class CheckoutSG(StatesGroup):
    waiting_for_cart = State()
    waiting_for_address = State()
    waiting_for_payment = State()


class NestedParentSG(StatesGroup):
    step_zero = State()


class NestedChildSG(NestedParentSG):
    step_one = State()


def test_state_registry_scan():
    registry = StateRegistry()
    tree = registry.scan()

    assert "CheckoutSG" in tree
    assert "CheckoutSG:waiting_for_cart" in tree["CheckoutSG"]
    assert "CheckoutSG:waiting_for_address" in tree["CheckoutSG"]
    assert "CheckoutSG:waiting_for_payment" in tree["CheckoutSG"]

    all_states = registry.get_all_states()
    assert "CheckoutSG:waiting_for_cart" in all_states
    assert "CheckoutSG:waiting_for_payment" in all_states
