"""
IT Support & Incident Desk Bot demonstrating aiogram-fsm-inspector.
Bot: @chgpgt_ru_bot
Port: 8082 (or auto-assigned)
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import sys
import time
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
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

from aiogram_fsm_inspector import setup_devtools


class SupportTicketSG(StatesGroup):
    selecting_department = State()
    describing_problem = State()
    awaiting_urgency = State()
    in_review = State()
    resolved = State()


async def main() -> None:
    load_env_file()
    logging.basicConfig(level=logging.INFO)

    bot_token = os.getenv("SUPPORT_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not bot_token:
        print("\n[Error] SUPPORT_BOT_TOKEN (or BOT_TOKEN) environment variable is not set.")
        print("Please set your bot token before running:")
        print("  Windows:    $env:SUPPORT_BOT_TOKEN='your_telegram_bot_token'")
        print("  Linux/Mac:  export SUPPORT_BOT_TOKEN='your_telegram_bot_token'\n")
        sys.exit(1)

    bot = Bot(token=bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # Configure devtools on port 8082 (auto-increments if port is busy)
    bundle = setup_devtools(dp, host="127.0.0.1", port=8082, auto_port=True)

    @dp.startup()
    async def on_startup(bot: Bot) -> None:
        me = await bot.get_me()
        print("\n" + "=" * 60)
        print(f" [Support Bot] @{me.username} ({me.first_name}) started!")
        actual_port = bundle.server_manager.port if bundle else 8082
        print(f" [aiogram-fsm-inspector] Web UI: http://127.0.0.1:{actual_port}")
        print("=" * 60 + "\n")

        # Seed realistic initial sessions for live inspection
        if bundle:
            # Seed Session 1: David (Critical Cloud Outage)
            key1 = StorageKey(bot_id=me.id, chat_id=901, user_id=901, destiny="default")
            await bundle.storage_proxy.set_state(key=key1, state=SupportTicketSG.in_review)
            await bundle.storage_proxy.set_data(
                key=key1,
                data={
                    "ticket_id": "INC-78401",
                    "department": "Infrastructure & Cloud",
                    "urgency": "CRITICAL",
                    "description": "502 Bad Gateway across Frankfurt cluster edge routers",
                    "sla_minutes_left": 14,
                    "assigned_sre": "Alex M. (Lead On-Call)",
                    "affected_users": 1450,
                    "servers": ["fra-01", "fra-02", "ams-05"],
                },
            )
            bundle.middleware._user_meta[901] = {
                "user_id": 901,
                "username": "david_ops",
                "full_name": "David Miller",
                "language_code": "en",
                "is_bot": False,
                "is_premium": True,
                "last_active_at": time.time() - 45,
                "last_event_type": "Message",
            }

            # Seed Session 2: Eva (Billing issue)
            key2 = StorageKey(bot_id=me.id, chat_id=902, user_id=902, destiny="default")
            await bundle.storage_proxy.set_state(key=key2, state=SupportTicketSG.awaiting_urgency)
            await bundle.storage_proxy.set_data(
                key=key2,
                data={
                    "ticket_id": "REQ-1044",
                    "department": "Billing & Payments",
                    "description": "Invoice #4928 double charged on Visa **** 4910",
                    "urgency": None,
                    "order_sum": 299.00,
                    "currency": "EUR",
                },
            )
            bundle.middleware._user_meta[902] = {
                "user_id": 902,
                "username": "eva_fin",
                "full_name": "Eva Rostova",
                "language_code": "ru",
                "is_bot": False,
                "is_premium": False,
                "last_active_at": time.time() - 500,
                "last_event_type": "Message",
            }

            # Seed Custom Presets
            bundle.snapshot_manager.create_preset(
                name="🔥 Production Outage (P0 Escalation)",
                state="SupportTicketSG:in_review",
                data={
                    "ticket_id": "INC-EMERGENCY",
                    "department": "Security & Core SRE",
                    "urgency": "BLOCKER",
                    "description": "Database connection pool exhausted in primary region",
                    "sla_minutes_left": 5,
                    "affected_users": 10000,
                },
                description="Критический инцидент первого приоритета для проверки алертов",
            )
            bundle.snapshot_manager.create_preset(
                name="💳 Regular Refund Request",
                state="SupportTicketSG:selecting_department",
                data={
                    "ticket_id": "REQ-0012",
                    "department": "Billing",
                    "urgency": "LOW",
                    "description": "User requested standard 14-day refund",
                },
                description="Стандартное обращение в отдел биллинга",
            )

    @dp.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext) -> None:
        ticket_num = f"TICK-{random.randint(1000, 9999)}"
        await state.set_state(SupportTicketSG.selecting_department)
        await state.set_data(
            {
                "ticket_id": ticket_num,
                "department": None,
                "urgency": "Normal",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        await message.answer(
            f"🛠 <b>Служба поддержки & Service Desk</b>\n"
            f"Создан черновик заявки: <code>{ticket_num}</code>\n\n"
            "Выберите отдел (напишите одно из слов):\n"
            "• <b>Billing</b> (счета, платежи)\n"
            "• <b>DevOps</b> (серверы, API, сбои)\n"
            "• <b>Security</b> (доступы, безопасность)\n\n"
            "Текущий FSM шаг: <code>SupportTicketSG:selecting_department</code>"
        )

    @dp.message(SupportTicketSG.selecting_department, F.text)
    async def process_dept(message: Message, state: FSMContext) -> None:
        dept = message.text.strip().capitalize()
        await state.update_data(department=dept)
        await state.set_state(SupportTicketSG.describing_problem)
        await message.answer(
            f"Отдел: <b>{dept}</b>.\n\n"
            "Опишите подробности вашей проблемы или ошибки текстом:\n"
            "FSM шаг: <code>SupportTicketSG:describing_problem</code>"
        )

    @dp.message(SupportTicketSG.describing_problem, F.text)
    async def process_desc(message: Message, state: FSMContext) -> None:
        desc = message.text.strip()
        await state.update_data(description=desc)
        await state.set_state(SupportTicketSG.awaiting_urgency)
        await message.answer(
            "Описание принято!\n\n"
            "Укажите приоритет срочности (напишите <b>Низкий</b>, <b>Средний</b> или <b>Критический</b>):\n"
            "FSM шаг: <code>SupportTicketSG:awaiting_urgency</code>"
        )

    @dp.message(SupportTicketSG.awaiting_urgency, F.text)
    async def process_urgency(message: Message, state: FSMContext) -> None:
        urg = message.text.strip().upper()
        data = await state.get_data()
        ticket_id = data.get("ticket_id", "TICK-UNKNOWN")

        await state.update_data(urgency=urg, status="Assigned to specialist")
        await state.set_state(SupportTicketSG.in_review)
        await message.answer(
            f"✅ Заявка <b>{ticket_id}</b> принята в работу!\n"
            f"Приоритет: <b>{urg}</b>\n"
            f"Отдел: {data.get('department')}\n\n"
            f"FSM шаг: <code>SupportTicketSG:in_review</code>\n"
            f"Инженер уже изучает ваш запрос. Напишите <b>закрыть</b> чтобы завершить."
        )

    @dp.message(SupportTicketSG.in_review, F.text)
    async def process_close(message: Message, state: FSMContext) -> None:
        await state.set_state(SupportTicketSG.resolved)
        await message.answer(
            "🎉 <b>Заявка успешно решена и закрыта!</b>\n"
            "Спасибо за обращение в техподдержку.\n\n"
            "FSM шаг: <code>SupportTicketSG:resolved</code>\n"
            "Вы можете протестировать смену состояний через панель aiogram-fsm-inspector!"
        )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
