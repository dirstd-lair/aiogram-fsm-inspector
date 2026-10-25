"""
Example bot demonstrating aiogram-fsm-inspector.
Run with:
    python examples/simple_bot.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def load_env_file() -> None:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

from aiogram_fsm_inspector import setup_devtools


class CheckoutSG(StatesGroup):
    waiting_for_name = State()
    waiting_for_address = State()
    waiting_for_payment = State()
    completed = State()


async def main() -> None:
    load_env_file()
    logging.basicConfig(level=logging.INFO)

    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        print("\n[Error] BOT_TOKEN environment variable is not set.")
        print("Please set your bot token before running:")
        print("  Windows:    $env:BOT_TOKEN='your_telegram_bot_token'")
        print("  Linux/Mac:  export BOT_TOKEN='your_telegram_bot_token'\n")
        sys.exit(1)

    bot = Bot(token=bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # One-line setup for inspector
    bundle = setup_devtools(dp, host="127.0.0.1", port=8080, auto_port=True)

    @dp.startup()
    async def on_startup(bot: Bot) -> None:
        me = await bot.get_me()
        actual_port = bundle.server_manager.port if bundle else 8080
        print("\n" + "=" * 60)
        print(f" [Telegram Bot] @{me.username} ({me.first_name}) started!")
        print(f" [aiogram-fsm-inspector] Web UI: http://127.0.0.1:{actual_port}")
        print("=" * 60 + "\n")

        # Seed initial session for live inspection
        if bundle:
            from aiogram.fsm.storage.base import StorageKey
            import time

            key = StorageKey(bot_id=me.id, chat_id=701, user_id=701, destiny="default")
            await bundle.storage_proxy.set_state(key=key, state=CheckoutSG.waiting_for_address)
            await bundle.storage_proxy.set_data(
                key=key,
                data={
                    "customer_name": "Alice Wonderland",
                    "cart": [101, 105, 204],
                    "total": 6800,
                    "currency": "RUB",
                    "delivery_type": "courier",
                    "items_count": 3,
                },
            )
            bundle.middleware._user_meta[701] = {
                "user_id": 701,
                "username": "alice_w",
                "full_name": "Alice Wonderland",
                "language_code": "ru",
                "is_bot": False,
                "is_premium": True,
                "last_active_at": time.time() - 30,
                "last_event_type": "Message",
            }

            bundle.snapshot_manager.create_preset(
                name="Готовый заказ (Оплата картой)",
                state="CheckoutSG:waiting_for_payment",
                data={
                    "customer_name": "Иван Тестовый",
                    "delivery_address": "г. Москва, ул. Ленина 12, кв. 4",
                    "cart": [101],
                    "total": 3200,
                    "currency": "RUB",
                },
                description="Шаг оплаты перед подтверждением",
            )

    @dp.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext) -> None:
        await state.set_state(CheckoutSG.waiting_for_name)
        await state.set_data({
            "cart": [101, 102],
            "total": 4500,
            "currency": "RUB",
            "items_count": 2,
        })
        await message.answer(
            "👋 Добро пожаловать в тестовый бот!\n"
            "Текущий FSM шаг: <b>CheckoutSG:waiting_for_name</b>\n\n"
            "Напишите ваше имя (или проверьте/измените состояние в веб-панели http://127.0.0.1:8080):"
        )

    @dp.message(CheckoutSG.waiting_for_name, F.text)
    async def process_name(message: Message, state: FSMContext) -> None:
        await state.update_data(customer_name=message.text)
        await state.set_state(CheckoutSG.waiting_for_address)
        await message.answer(
            f"Отлично, {message.text}!\n"
            "Текущий FSM шаг: <b>CheckoutSG:waiting_for_address</b>\n\n"
            "Теперь введите адрес доставки:"
        )

    @dp.message(CheckoutSG.waiting_for_address, F.text)
    async def process_address(message: Message, state: FSMContext) -> None:
        await state.update_data(delivery_address=message.text)
        await state.set_state(CheckoutSG.waiting_for_payment)
        await message.answer(
            "Адрес сохранен!\n"
            "Текущий FSM шаг: <b>CheckoutSG:waiting_for_payment</b>\n\n"
            "Введите способ оплаты (карта / наличные / крипта):"
        )

    @dp.message(CheckoutSG.waiting_for_payment, F.text)
    async def process_payment(message: Message, state: FSMContext) -> None:
        await state.update_data(payment_method=message.text, is_paid=True)
        await state.set_state(CheckoutSG.completed)
        data = await state.get_data()
        await message.answer(
            f"🎉 Заказ оформлен!\n"
            f"FSM шаг: <b>CheckoutSG:completed</b>\n"
            f"Имя: {data.get('customer_name')}\n"
            f"Адрес: {data.get('delivery_address')}\n"
            f"Оплата: {data.get('payment_method')}\n\n"
            f"Вы можете сбросить состояние командой /start или через веб-инспектор."
        )

    print("\n" + "=" * 60)
    print(" [aiogram-fsm-inspector] Web UI: http://127.0.0.1:8080")
    print(" [Telegram Bot] polling started successfully!")
    print("=" * 60 + "\n")

    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
