"""
Quiz / Vocabulary Learning Bot demonstrating aiogram-fsm-inspector.
Bot: @learning_words_ai_bot
Port: 8081 (or auto-assigned)
"""

from __future__ import annotations

import asyncio
import logging
import os
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
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from aiogram_fsm_inspector import setup_devtools


class WordQuizSG(StatesGroup):
    choosing_topic = State()
    learning_card = State()
    answering_quiz = State()
    streak_celebrated = State()
    completed = State()


def get_topics_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💻 IT & Tech", callback_data="topic_it"),
                InlineKeyboardButton(text="✈️ Travel", callback_data="topic_travel"),
            ],
            [
                InlineKeyboardButton(text="🍕 Food & Cooking", callback_data="topic_food"),
                InlineKeyboardButton(text="💼 Business", callback_data="topic_business"),
            ],
        ]
    )


async def main() -> None:
    load_env_file()
    logging.basicConfig(level=logging.INFO)

    bot_token = os.getenv("QUIZ_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not bot_token:
        print("\n[Error] QUIZ_BOT_TOKEN (or BOT_TOKEN) environment variable is not set.")
        print("Please set your bot token before running:")
        print("  Windows:    $env:QUIZ_BOT_TOKEN='your_telegram_bot_token'")
        print("  Linux/Mac:  export QUIZ_BOT_TOKEN='your_telegram_bot_token'\n")
        sys.exit(1)

    bot = Bot(token=bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # Configure devtools on port 8081 (auto-increments if port is busy)
    bundle = setup_devtools(dp, host="127.0.0.1", port=8081, auto_port=True)

    @dp.startup()
    async def on_startup(bot: Bot) -> None:
        me = await bot.get_me()
        print("\n" + "=" * 60)
        print(f" [Quiz Bot] @{me.username} ({me.first_name}) started!")
        actual_port = bundle.server_manager.port if bundle else 8081
        print(f" [aiogram-fsm-inspector] Web UI: http://127.0.0.1:{actual_port}")
        print("=" * 60 + "\n")

        # Seed realistic initial sessions for live inspection
        if bundle:
            # Seed Session 1: Bob (IT Quiz)
            key1 = StorageKey(bot_id=me.id, chat_id=801, user_id=801, destiny="default")
            await bundle.storage_proxy.set_state(key=key1, state=WordQuizSG.answering_quiz)
            await bundle.storage_proxy.set_data(
                key=key1,
                data={
                    "topic": "IT & Tech",
                    "difficulty": "B2",
                    "current_word": "idempotent",
                    "question": "What does idempotent mean in API design?",
                    "score": 92,
                    "streak_days": 14,
                    "words_reviewed": ["concurrency", "latency", "mutex"],
                    "mistakes_count": 1,
                },
            )
            bundle.middleware._user_meta[801] = {
                "user_id": 801,
                "username": "bob_developer",
                "full_name": "Bob Martin",
                "language_code": "en",
                "is_bot": False,
                "is_premium": True,
                "last_active_at": time.time() - 120,
                "last_event_type": "Message",
            }

            # Seed Session 2: Clara (Travel Card)
            key2 = StorageKey(bot_id=me.id, chat_id=802, user_id=802, destiny="default")
            await bundle.storage_proxy.set_state(key=key2, state=WordQuizSG.learning_card)
            await bundle.storage_proxy.set_data(
                key=key2,
                data={
                    "topic": "Travel",
                    "difficulty": "A2",
                    "current_card": {
                        "term": "layover",
                        "translation": "пересадка между рейсами",
                        "example": "We had a four-hour layover in Frankfurt.",
                    },
                    "score": 35,
                    "streak_days": 3,
                    "daily_goal": 10,
                },
            )
            bundle.middleware._user_meta[802] = {
                "user_id": 802,
                "username": "clara_wanderlust",
                "full_name": "Clara Oswald",
                "language_code": "ru",
                "is_bot": False,
                "is_premium": False,
                "last_active_at": time.time() - 360,
                "last_event_type": "CallbackQuery",
            }

            # Seed Custom Presets
            bundle.snapshot_manager.create_preset(
                name="C1 Vocab Master (Score 95+)",
                state="WordQuizSG:answering_quiz",
                data={
                    "topic": "Business & Legal",
                    "difficulty": "C1",
                    "score": 98,
                    "streak_days": 45,
                    "current_word": "indemnification",
                    "words_reviewed": ["mitigation", "arbitration", "liability"],
                },
                description="Студент уровня Advanced с высоким винрейтом",
            )
            bundle.snapshot_manager.create_preset(
                name="A1 Beginner Clean Slate",
                state="WordQuizSG:choosing_topic",
                data={"score": 0, "streak_days": 1, "topic": None},
                description="Новый ученик выбирает первую категорию слов",
            )

    @dp.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext) -> None:
        await state.set_state(WordQuizSG.choosing_topic)
        await state.set_data(
            {
                "score": 0,
                "streak_days": 1,
                "topic": None,
                "words_reviewed": [],
                "user_joined": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        await message.answer(
            "🧠 <b>Добро пожаловать в Word Quiz Bot!</b>\n\n"
            "Выберите тему для изучения слов:\n"
            "• Напишите: <i>IT</i>, <i>Travel</i>, <i>Food</i> или <i>Business</i>\n\n"
            "Текущий FSM шаг: <code>WordQuizSG:choosing_topic</code>\n"
            "Вы можете отслеживать и менять состояние в панели aiogram-devtools!"
        )

    @dp.message(WordQuizSG.choosing_topic, F.text)
    async def process_topic(message: Message, state: FSMContext) -> None:
        topic = message.text.strip()
        await state.update_data(topic=topic, current_word="ephemeral")
        await state.set_state(WordQuizSG.learning_card)
        await message.answer(
            f"Тема выбрана: <b>{topic}</b>!\n\n"
            "📖 Ваша карточка:\n"
            "Слово: <b>Ephemeral</b> [ɪˈfem(ə)rəl]\n"
            "Перевод: <i>мимолётный, эфемерный</i>\n"
            "Пример: <i>Fame in the digital age is often ephemeral.</i>\n\n"
            "Напишите <b>тест</b> или <b>дальше</b> чтобы проверить знания!\n"
            "FSM шаг: <code>WordQuizSG:learning_card</code>"
        )

    @dp.message(WordQuizSG.learning_card, F.text)
    async def process_card_next(message: Message, state: FSMContext) -> None:
        await state.update_data(
            question="What is the antonym of 'Ephemeral'?",
            correct_answer="Eternal",
            options=["Brief", "Eternal", "Fleeting"],
        )
        await state.set_state(WordQuizSG.answering_quiz)
        await message.answer(
            "❓ <b>Вопрос викторины:</b>\n"
            "Каков антоним слова <i>Ephemeral</i>?\n\n"
            "Варианты ответа:\n"
            "1. Brief\n"
            "2. Eternal\n"
            "3. Fleeting\n\n"
            "Напишите номер ответа или слово:\n"
            "FSM шаг: <code>WordQuizSG:answering_quiz</code>"
        )

    @dp.message(WordQuizSG.answering_quiz, F.text)
    async def process_quiz_answer(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        ans = message.text.strip().lower()
        is_correct = ans in ("2", "eternal")

        score = data.get("score", 0) + (10 if is_correct else 0)
        streak = data.get("streak_days", 1) + (1 if is_correct else 0)

        await state.update_data(score=score, streak_days=streak, last_answer_correct=is_correct)

        if is_correct:
            await state.set_state(WordQuizSG.streak_celebrated)
            await message.answer(
                f"🎉 <b>Правильно!</b> (+10 очков)\n"
                f"Текущий счет: <b>{score}</b> | Стрик: 🔥 <b>{streak} дн.</b>\n\n"
                f"FSM шаг: <code>WordQuizSG:streak_celebrated</code>\n"
                f"Напишите <b>завершить</b> или <b>еще</b>!"
            )
        else:
            await state.set_state(WordQuizSG.completed)
            await message.answer(
                f"❌ <b>Неверно!</b> Правильный ответ был <i>Eternal</i>.\n"
                f"Текущий счет: {score}\n\n"
                f"FSM шаг: <code>WordQuizSG:completed</code>\n"
                f"Напишите /start чтобы начать заново."
            )

    @dp.message(WordQuizSG.streak_celebrated, F.text)
    async def process_celebration(message: Message, state: FSMContext) -> None:
        await state.set_state(WordQuizSG.completed)
        await message.answer(
            "🏆 <b>Урок завершён!</b> Отличный результат!\n"
            "FSM шаг: <code>WordQuizSG:completed</code>\n"
            "Для новой тренировки введите /start или выберите пресет в веб-инспекторе."
        )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
