import os
from aiohttp import web
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from bot.handlers import router
from bot.db import init_db, close_db
from bot.runtime import init_runtime, close_runtime


def must_getenv(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"ENV {name} is required")
    return v


async def on_startup(bot: Bot):
    public_base = os.getenv("PUBLIC_BASE_URL")
    secret = must_getenv("WEBHOOK_SECRET")

    if public_base:
        webhook_url = f"{public_base.rstrip('/')}/webhook/{secret}"
        await bot.set_webhook(
            url=webhook_url,
            secret_token=secret,
            drop_pending_updates=True,
        )
        print(f"[startup] webhook set: {webhook_url}")
    else:
        print("[startup] PUBLIC_BASE_URL not set -> webhook will NOT be set")


async def on_shutdown(bot: Bot):
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass


def create_app() -> web.Application:
    load_dotenv()

    token = must_getenv("BOT_TOKEN")
    bot = Bot(token=token, parse_mode=ParseMode.HTML)

    # DB + внешние API
    db_path = os.getenv("DB_PATH", "data.db")
    init_db(db_path=db_path)

    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
    ua = os.getenv("USER_AGENT", "psych-bot/1.0")
    init_runtime(mailto=mailto, user_agent=ua)

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(router)

    app = web.Application()
    secret = must_getenv("WEBHOOK_SECRET")

    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret).register(
        app, path=f"/webhook/{secret}"
    )

    async def health(_):
        return web.json_response({"ok": True})

    app.router.add_get("/health", health)

    setup_application(app, dp, bot=bot)

    async def _startup(_app: web.Application):
        await on_startup(bot)

    async def _shutdown(_app: web.Application):
        await on_shutdown(bot)
        await close_runtime()
        close_db()
        await bot.session.close()

    app.on_startup.append(_startup)
    app.on_shutdown.append(_shutdown)
    return app


if __name__ == "__main__":
    # Для деплоя с webhook. Для сдачи практики используйте main.py (polling): python main.py
    app = create_app()
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    web.run_app(app, host=host, port=port)
