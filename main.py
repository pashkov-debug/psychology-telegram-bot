import asyncio
import os

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import router
from bot.db import init_db, close_db
from bot.runtime import init_runtime, close_runtime


def must_getenv(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"ENV {name} is required")
    return v


async def main() -> None:
    load_dotenv()

    # --- Конфиг ---
    token = must_getenv("BOT_TOKEN")
    db_path = os.getenv("DB_PATH", "data.db")

    # Crossref рекомендует указывать mailto для "polite pool".
    # Если не хотите — оставьте пустым. См. доки Crossref.
    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
    ua = os.getenv("USER_AGENT", "psych-bot/1.0")

    # --- Инициализация окружения ---
    init_db(db_path=db_path)
    init_runtime(mailto=mailto, user_agent=ua)

    # --- Telegram ---
    bot = Bot(token=token, parse_mode=ParseMode.HTML)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await close_runtime()
        close_db()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
