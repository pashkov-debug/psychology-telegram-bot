import os
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
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
    token = must_getenv("BOT_TOKEN")
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # DB + внешний API
    db_path = os.getenv("DB_PATH", "data.db")
    init_db(db_path=db_path)

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
    # Для Web Service (webhook). Для Background Worker на Render используйте main.py (polling).
    port = int(os.getenv("PORT", "10000"))
    web.run_app(create_app(), host="0.0.0.0", port=port)
