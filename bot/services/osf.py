from __future__ import annotations

import asyncio
from typing import Any, Optional

import aiohttp

from ._common import Paper, ProviderError, RateLimiter, normalize_doi

OSF_BASE = "https://api.osf.io/v2"


class OsfError(ProviderError):
    pass


class OsfPreprintsClient:
    def __init__(self, session: aiohttp.ClientSession, user_agent: str = "psych-bot/1.0", provider: str = "psyarxiv"):
        self._session = session
        self._ua = user_agent or "psych-bot/1.0"
        self._provider = (provider or "psyarxiv").strip()
        self._limiter = RateLimiter(min_interval=0.25)

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        await self._limiter.wait()
        url = f"{OSF_BASE}{path}"
        headers = {"User-Agent": self._ua}
        try:
            async with self._session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=18)) as r:
                if r.status >= 400:
                    txt = await r.text()
                    raise OsfError(f"OSF HTTP {r.status}: {txt[:300]}")
                return await r.json()
        except asyncio.TimeoutError as e:
            raise OsfError("Таймаут при обращении к OSF.") from e
        except aiohttp.ClientError as e:
            raise OsfError("Сетевая ошибка при обращении к OSF.") from e

    @staticmethod
    def _to_paper(obj: dict[str, Any]) -> Paper:
        attrs = obj.get("attributes") or {}
        if not isinstance(attrs, dict):
            attrs = {}

        title = (attrs.get("title") or "").strip() or "(без названия)"
        doi = (attrs.get("doi") or "").strip() or None
        if doi:
            doi = normalize_doi(doi).rstrip(").,;")

        year = None
        # date_published / date_created -> YYYY-MM-DD
        for k in ("date_published", "date_created", "date_modified"):
            v = str(attrs.get(k) or "").strip()
            if len(v) >= 4 and v[:4].isdigit():
                try:
                    year = int(v[:4])
                    break
                except Exception:
                    pass

        links = obj.get("links") or {}
        url = None
        if isinstance(links, dict):
            url = (links.get("html") or "").strip() or None
        if not url and doi:
            url = f"https://doi.org/{doi}"

        return Paper(title=title, year=year, doi=doi, url=url, authors="", source="osf")

    async def search_title(self, title: str, rows: int = 5) -> list[Paper]:
        q = (title or "").strip()
        if not q:
            return []
        params = {
            "filter[provider]": self._provider,
            "filter[title]": q,
            "page[size]": int(rows),
        }
        data = await self._get_json("/preprints/", params=params)
        items = (data or {}).get("data") or []
        if not isinstance(items, list):
            return []
        return [self._to_paper(it) for it in items if isinstance(it, dict)]

    async def lookup_doi(self, doi: str) -> Optional[Paper]:
        d = normalize_doi(doi).rstrip(").,;")
        if not d:
            return None
        params = {
            "filter[provider]": self._provider,
            "filter[doi]": d,
            "page[size]": 1,
        }
        data = await self._get_json("/preprints/", params=params)
        items = (data or {}).get("data") or []
        if isinstance(items, list) and items:
            it = items[0]
            if isinstance(it, dict):
                return self._to_paper(it)
        return None
