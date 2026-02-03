from __future__ import annotations

from typing import Optional

import aiohttp

from bot.services import Services, init_services
from bot.services.crossref import CrossrefClient
from bot.services.literature import LiteratureService


_http: Optional[aiohttp.ClientSession] = None
_services: Optional[Services] = None


def init_runtime(
    mailto: str = "",
    user_agent: str = "psych-bot/1.0",
    # дополнительные параметры (все опциональны)
    ncbi_api_key: str = "",
    ncbi_email: str = "",
    ncbi_tool: str = "psych-bot",
    plos_api_key: str = "",
    semanticscholar_api_key: str = "",
    doaj_api_key: str = "",
    osf_provider: str = "psyarxiv",
) -> None:
    """Создаёт общий aiohttp session и клиентов внешних API."""
    global _http, _services
    if _http is None or _http.closed:
        _http = aiohttp.ClientSession()

    _services = init_services(
        session=_http,
        user_agent=user_agent,
        mailto=mailto,
        ncbi_api_key=ncbi_api_key,
        ncbi_email=ncbi_email,
        ncbi_tool=ncbi_tool,
        plos_api_key=plos_api_key,
        semanticscholar_api_key=semanticscholar_api_key,
        doaj_api_key=doaj_api_key,
        osf_provider=osf_provider,
    )


def get_services() -> Services:
    if _services is None:
        raise RuntimeError("Services не инициализированы. Вызовите init_runtime() при старте приложения.")
    return _services


def get_literature() -> LiteratureService:
    return get_services().literature


# Backward compatibility (старые хендлеры)
def get_crossref() -> CrossrefClient:
    return get_services().crossref


async def close_runtime() -> None:
    global _http, _services
    _services = None
    if _http is not None and not _http.closed:
        await _http.close()
    _http = None
