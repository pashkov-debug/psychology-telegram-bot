from __future__ import annotations

import asyncio
from typing import Any, Optional

import aiohttp

from ._common import Paper, ProviderError, RateLimiter, normalize_doi

S2_BASE = "https://api.semanticscholar.org/graph/v1"


class SemanticScholarError(ProviderError):
    pass


class SemanticScholarClient:
    def __init__(self, session: aiohttp.ClientSession, api_key: str = "", user_agent: str = "psych-bot/1.0"):
        self._session = session
        self._key = (api_key or "").strip()
        self._ua = user_agent or "psych-bot/1.0"
        self._limiter = RateLimiter(min_interval=0.2 if self._key else 1.0)

    def _headers(self) -> dict[str, str]:
        h = {"User-Agent": self._ua}
        if self._key:
            # По документации ключ передают в заголовке
            h["x-api-key"] = self._key
        return h

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        await self._limiter.wait()
        url = f"{S2_BASE}{path}"
        try:
            async with self._session.get(
                url,
                params=params,
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=16),
            ) as r:
                if r.status >= 400:
                    txt = await r.text()
                    raise SemanticScholarError(f"Semantic Scholar HTTP {r.status}: {txt[:300]}")
                return await r.json()
        except asyncio.TimeoutError as e:
            raise SemanticScholarError("Таймаут при обращении к Semantic Scholar.") from e
        except aiohttp.ClientError as e:
            raise SemanticScholarError("Сетевая ошибка при обращении к Semantic Scholar.") from e

    @staticmethod
    def _authors(a: Any) -> str:
        if not isinstance(a, list) or not a:
            return ""
        names = []
        for it in a[:4]:
            if isinstance(it, dict):
                name = (it.get("name") or "").strip()
                if name:
                    names.append(name)
        tail = " и др." if len(a) > 4 else ""
        return ", ".join(names) + tail

    @staticmethod
    def _to_paper(obj: dict[str, Any]) -> Paper:
        title = (obj.get("title") or "").strip() or "(без названия)"
        year = obj.get("year")
        if not isinstance(year, int):
            year = None

        doi = None
        ext = obj.get("externalIds") or {}
        if isinstance(ext, dict):
            v = (ext.get("DOI") or "").strip()
            if v:
                doi = normalize_doi(v).rstrip(").,;")

        url = (obj.get("url") or "").strip() or (f"https://doi.org/{doi}" if doi else None)
        cited_by = obj.get("citationCount")
        if not isinstance(cited_by, int):
            cited_by = None

        return Paper(
            title=title,
            year=year,
            doi=doi,
            url=url,
            authors=SemanticScholarClient._authors(obj.get("authors")),
            source="semanticscholar",
            cited_by=cited_by,
        )

    async def search_title(self, title: str, rows: int = 5) -> list[Paper]:
        q = (title or "").strip()
        if not q:
            return []
        data = await self._get_json(
            "/paper/search",
            params={
                "query": q,
                "limit": int(rows),
                "fields": "title,year,authors,url,citationCount,externalIds",
            },
        )
        items = (data or {}).get("data") or []
        if not isinstance(items, list):
            return []
        out: list[Paper] = []
        for it in items:
            if isinstance(it, dict):
                out.append(self._to_paper(it))
        return out

    async def lookup_doi(self, doi: str) -> Optional[Paper]:
        d = normalize_doi(doi).rstrip(").,;")
        if not d:
            return None
        data = await self._get_json(
            f"/paper/DOI:{d}",
            params={"fields": "title,year,authors,url,citationCount,externalIds"},
        )
        if isinstance(data, dict) and data.get("title"):
            return self._to_paper(data)
        return None
