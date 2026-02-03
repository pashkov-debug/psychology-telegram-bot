from __future__ import annotations

import asyncio
from typing import Any, Optional

import aiohttp

from ._common import Paper, ProviderError, RateLimiter, normalize_doi

BIORXIV_BASE = "https://api.biorxiv.org"


class BiorxivError(ProviderError):
    pass


class BiorxivClient:
    """bioRxiv/medRxiv API. Реально удобно для lookup по DOI."""

    def __init__(self, session: aiohttp.ClientSession, user_agent: str = "psych-bot/1.0", server: str = "biorxiv"):
        self._session = session
        self._ua = user_agent or "psych-bot/1.0"
        self._server = server  # "biorxiv" или "medrxiv"
        self._limiter = RateLimiter(min_interval=0.2)

    async def _get_json(self, path: str) -> dict[str, Any]:
        await self._limiter.wait()
        url = f"{BIORXIV_BASE}{path}"
        headers = {"User-Agent": self._ua}
        try:
            async with self._session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=18)) as r:
                if r.status >= 400:
                    txt = await r.text()
                    raise BiorxivError(f"bioRxiv HTTP {r.status}: {txt[:300]}")
                return await r.json()
        except asyncio.TimeoutError as e:
            raise BiorxivError("Таймаут при обращении к bioRxiv/medRxiv.") from e
        except aiohttp.ClientError as e:
            raise BiorxivError("Сетевая ошибка при обращении к bioRxiv/medRxiv.") from e

    @staticmethod
    def _to_paper(obj: dict[str, Any], server: str) -> Paper:
        title = (obj.get("title") or "").strip() or "(без названия)"
        authors = (obj.get("authors") or "").strip()
        doi = (obj.get("doi") or "").strip() or None
        if doi:
            doi = normalize_doi(doi).rstrip(").,;")
        year = None
        date = str(obj.get("date") or "").strip()
        if len(date) >= 4 and date[:4].isdigit():
            try:
                year = int(date[:4])
            except Exception:
                year = None
        url = f"https://doi.org/{doi}" if doi else None
        return Paper(title=title, year=year, doi=doi, url=url, authors=authors, source=server)

    async def search_title(self, title: str, rows: int = 5) -> list[Paper]:
        # API не поддерживает прямой title-search без тяжёлых проходов по интервалам.
        return []

    async def lookup_doi(self, doi: str) -> Optional[Paper]:
        d = normalize_doi(doi).rstrip(").,;")
        if not d:
            return None
        data = await self._get_json(f"/details/{self._server}/{d}/na/json")
        col = (data or {}).get("collection") or []
        if isinstance(col, list) and col:
            obj = col[0]
            if isinstance(obj, dict):
                return self._to_paper(obj, server=self._server)
        return None
