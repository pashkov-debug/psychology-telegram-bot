from __future__ import annotations

from typing import Optional

import aiohttp

from bot.services.crossref import CrossrefClient


_http: Optional[aiohttp.ClientSession] = None
_crossref: Optional[CrossrefClient] = None


def init_runtime(mailto: str = "", user_agent: str = "psych-bot/1.0") -> None:
    """Создаёт общий HTTP session и клиент Crossref."""
    global _http, _crossref
    if _http is None or _http.closed:
        _http = aiohttp.ClientSession()
    _crossref = CrossrefClient(session=_http, mailto=mailto, user_agent=user_agent)


def get_crossref() -> CrossrefClient:
    if _crossref is None:
        raise RuntimeError("CrossrefClient не инициализирован. Вызовите init_runtime() при старте приложения.")
    return _crossref


async def close_runtime() -> None:
    global _http, _crossref
    _crossref = None
    if _http is not None and not _http.closed:
        await _http.close()
    _http = None
