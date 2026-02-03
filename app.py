import asyncio
import logging
import os

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import router


def must_getenv(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"ENV {name} is required")
    return v


async def main() -> None:
    load_dotenv()

    # Логи в stdout — Render их подхватит
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    log = logging.getLogger("worker")

    token = must_getenv("BOT_TOKEN")

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(router)

    # Критично: если раньше был webhook — снимаем его, иначе polling не увидит апдейты
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("Webhook disabled (delete_webhook ok). Using long polling.")
    except Exception:
        log.exception("Failed to delete webhook (continuing).")

    try:
        # allowed_updates — только используемые типы апдейтов (меньше трафик)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        log.info("Bot session closed.")


if __name__ == "__main__":
    asyncio.run(main())
