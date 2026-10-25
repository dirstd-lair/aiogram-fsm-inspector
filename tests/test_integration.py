from __future__ import annotations

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, Update, User

from aiogram_fsm_inspector import DevToolsStorageProxy, setup_devtools


class RegistrationSG(StatesGroup):
    name = State()
    email = State()


@pytest.mark.asyncio
async def test_setup_devtools_integration():
    dp = Dispatcher(storage=MemoryStorage())

    # Ensure dual replacement rule
    bundle = setup_devtools(dp, host="127.0.0.1", port=8080)
    assert bundle is not None

    assert isinstance(dp.storage, DevToolsStorageProxy)
    assert isinstance(dp.fsm.storage, DevToolsStorageProxy)
    assert dp.storage is dp.fsm.storage

    # Check state tree discovered RegistrationSG
    tree = bundle.state_registry.get_tree()
    assert "RegistrationSG" in tree
    assert "RegistrationSG:name" in tree["RegistrationSG"]

    # Handler to test state mutation through FSMContext
    @dp.message()
    async def name_handler(message: Message, state: FSMContext):
        await state.set_state(RegistrationSG.email)
        await state.update_data(name="Alex")

    bot = Bot(token="1234567890:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")

    user = User(id=777, is_bot=False, first_name="Alex", username="alexdev")
    chat = Chat(id=777, type="private")
    msg = Message(
        message_id=1,
        date=12345678,
        chat=chat,
        from_user=user,
        text="Hello",
    )
    update = Update(update_id=1, message=msg)

    # Feed update to dispatcher
    await dp.feed_update(bot, update)

    # Verify session is tracked in proxy and state changed
    known_keys = list(bundle.storage_proxy.known_keys)
    assert len(known_keys) == 1
    key = known_keys[0]
    assert key.user_id == 777

    curr_state = await bundle.storage_proxy.get_state(key)
    assert curr_state == "RegistrationSG:email"

    curr_data = await bundle.storage_proxy.get_data(key)
    assert curr_data["name"] == "Alex"

    # Verify metadata captured by middleware
    meta = bundle.middleware.get_user_meta(777)
    assert meta is not None
    assert meta["username"] == "alexdev"

    await bot.session.close()
