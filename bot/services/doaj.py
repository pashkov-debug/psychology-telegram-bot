from __future__ import annotations

import asyncio
from typing import Any, Optional
from urllib.parse import quote

import aiohttp

from ._common import Paper, ProviderError, RateLimiter, normalize_doi

DOAJ_BASE = "https://doaj.org/api/v2"


class DoajError(ProviderError):
    pass


class DoajClient:
    """
    DOAJ Public Search API.

    ⚠️ Примечание: у DOAJ синтаксис query-параметра исторически менялся.
    Мы используем безопасную стратегию:
      - пробуем fielded-запрос (hypothesis),
      - если получили 0 результатов — пробуем простой текстовый запрос.
    """

    def __init__(self, session: aiohttp.ClientSession, api_key: str = "", user_agent: str = "psych-bot/1.0"):
        self._session = session
        self._key = (api_key or "").strip()
        self._ua = user_agent or "psych-bot/1.0"
        self._limiter = RateLimiter(min_interval=0.25)

    def _headers(self) -> dict[str, str]:
        h = {"User-Agent": self._ua}
        # Hypothesis: некоторые инстансы принимают Bearer, но публичный поиск обычно работает без ключа.
        if self._key:
            h["Authorization"] = f"Bearer {self._key}"
        return h

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        await self._limiter.wait()
        url = f"{DOAJ_BASE}{path}"
        try:
            async with self._session.get(url, params=params, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=16)) as r:
                if r.status >= 400:
                    txt = await r.text()
                    raise DoajError(f"DOAJ HTTP {r.status}: {txt[:300]}")
                return await r.json()
        except asyncio.TimeoutError as e:
            raise DoajError("Таймаут при обращении к DOAJ.") from e
        except aiohttp.ClientError as e:
            raise DoajError("Сетевая ошибка при обращении к DOAJ.") from e

    @staticmethod
    def _pick_doi(bib: dict[str, Any]) -> Optional[str]:
        for ident in (bib.get("identifier") or []):
            if not isinstance(ident, dict):
                continue
            t = str(ident.get("type") or ident.get("idtype") or "").lower()
            v = str(ident.get("id") or ident.get("value") or "").strip()
            if t == "doi" and v:
                return normalize_doi(v).rstrip(").,;")
        return None

    @staticmethod
    def _authors(bib: dict[str, Any]) -> str:
        a = bib.get("author") or []
        if not isinstance(a, list) or not a:
            return ""
        names = []
        for it in a[:4]:
            if isinstance(it, dict):
                name = (it.get("name") or "").strip()
                if name:
                    names.append(name)
            else:
                s = str(it).strip()
                if s:
                    names.append(s)
        tail = " и др." if len(a) > 4 else ""
        return ", ".join(names) + tail

    @staticmethod
    def _url(bib: dict[str, Any], doi: Optional[str]) -> Optional[str]:
        for link in (bib.get("link") or []):
            if isinstance(link, dict):
                u = (link.get("url") or "").strip()
                if u:
                    return u
        if doi:
            return f"https://doi.org/{doi}"
        return None

    @staticmethod
    def _to_paper(item: dict[str, Any]) -> Paper:
        bib = item.get("bibjson") or {}
        if not isinstance(bib, dict):
            bib = {}
        title = (bib.get("title") or "").strip() or "(без названия)"
        year = bib.get("year")
        if not isinstance(year, int):
            try:
                year = int(str(year)) if year else None
            except Exception:
                year = None
        doi = DoajClient._pick_doi(bib)
        return Paper(
            title=title,
            year=year,
            doi=doi,
            url=DoajClient._url(bib, doi),
            authors=DoajClient._authors(bib),
            source="doaj",
        )

    async def _search_raw(self, query: str, rows: int) -> list[Paper]:
        # В v2 query идёт прямо в path: /search/articles/{query}
        qpath = "/search/articles/" + quote(query, safe="")
        data = await self._get_json(qpath, params={"pageSize": int(rows)})
        results = (data or {}).get("results") or []
        if not isinstance(results, list):
            return []
        return [self._to_paper(it) for it in results if isinstance(it, dict)]

    async def search_title(self, title: str, rows: int = 5) -> list[Paper]:
        q = (title or "").strip()
        if not q:
            return []
        # Hypothesis: field может называться bibjson.title
        items = await self._search_raw(f'bibjson.title:"{q}"', rows=rows)
        if items:
            return items
        return await self._search_raw(q, rows=rows)

    async def lookup_doi(self, doi: str) -> Optional[Paper]:
        d = normalize_doi(doi).rstrip(").,;")
        if not d:
            return None
        # Hypothesis: поле для DOI внутри bibjson.identifier
        items = await self._search_raw(f'bibjson.identifier.id:"{d}"', rows=1)
        if not items:
            items = await self._search_raw(d, rows=1)
        return items[0] if items else None
