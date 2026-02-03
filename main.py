import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
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
    token = must_getenv("BOT_TOKEN")
    db_path = os.getenv("DB_PATH", "data.db")

    # Polite pool / User-Agent (рекомендуется для Crossref/OpenAlex и др.)
    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
    ua = os.getenv("USER_AGENT", "psych-bot/1.0").strip() or "psych-bot/1.0"

    # (опционально) ключи к внешним источникам
    ncbi_api_key = os.getenv("NCBI_API_KEY", "").strip()
    ncbi_email = os.getenv("NCBI_EMAIL", "").strip()
    ncbi_tool = os.getenv("NCBI_TOOL", "psych-bot").strip() or "psych-bot"

    plos_api_key = os.getenv("PLOS_API_KEY", "").strip()
    semanticscholar_api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    doaj_api_key = os.getenv("DOAJ_API_KEY", "").strip()
    osf_provider = os.getenv("OSF_PROVIDER", "psyarxiv").strip() or "psyarxiv"

    # Инициализация
    init_db(db_path=db_path)
    init_runtime(
        mailto=mailto,
        user_agent=ua,
        ncbi_api_key=ncbi_api_key,
        ncbi_email=ncbi_email,
        ncbi_tool=ncbi_tool,
        plos_api_key=plos_api_key,
        semanticscholar_api_key=semanticscholar_api_key,
        doaj_api_key=doaj_api_key,
        osf_provider=osf_provider,
    )

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # На Render (polling) важно снять webhook, иначе getUpdates не работает
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass

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
