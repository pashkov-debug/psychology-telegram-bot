from __future__ import annotations

import asyncio
from typing import Any, Optional
from urllib.parse import quote

import aiohttp

from ._common import Paper, ProviderError, RateLimiter, normalize_doi

OPENALEX_BASE = "https://api.openalex.org"


class OpenAlexError(ProviderError):
    pass


class OpenAlexClient:
    def __init__(self, session: aiohttp.ClientSession, mailto: str = "", user_agent: str = "psych-bot/1.0"):
        self._session = session
        self._mailto = (mailto or "").strip()
        self._ua = user_agent or "psych-bot/1.0"
        self._limiter = RateLimiter(min_interval=0.05)  # OpenAlex допускает высокие rps, но всё равно не спамим

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        await self._limiter.wait()
        url = f"{OPENALEX_BASE}{path}"
        headers = {"User-Agent": self._ua}
        if params is None:
            params = {}
        if self._mailto:
            params = {**params, "mailto": self._mailto}

        try:
            async with self._session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=14)) as r:
                if r.status >= 400:
                    txt = await r.text()
                    raise OpenAlexError(f"OpenAlex HTTP {r.status}: {txt[:300]}")
                return await r.json()
        except asyncio.TimeoutError as e:
            raise OpenAlexError("Таймаут при обращении к OpenAlex.") from e
        except aiohttp.ClientError as e:
            raise OpenAlexError("Сетевая ошибка при обращении к OpenAlex.") from e

    @staticmethod
    def _authors_from_work(w: dict[str, Any]) -> str:
        authorships = w.get("authorships") or []
        if not isinstance(authorships, list) or not authorships:
            return ""
        names = []
        for a in authorships[:4]:
            if not isinstance(a, dict):
                continue
            author = a.get("author") or {}
            if isinstance(author, dict):
                name = (author.get("display_name") or "").strip()
                if name:
                    names.append(name)
        tail = " и др." if len(authorships) > 4 else ""
        return ", ".join(names) + tail

    @staticmethod
    def _to_paper(w: dict[str, Any]) -> Paper:
        title = (w.get("title") or "").strip() or "(без названия)"
        year = w.get("publication_year")
        if not isinstance(year, int):
            year = None

        doi = (w.get("doi") or "").strip() or None
        if doi:
            doi = normalize_doi(doi).rstrip(").,;")

        url = None
        primary = w.get("primary_location") or {}
        if isinstance(primary, dict):
            url = (primary.get("landing_page_url") or "").strip() or None
        if not url and doi:
            url = f"https://doi.org/{doi}"

        cited_by = w.get("cited_by_count")
        if not isinstance(cited_by, int):
            cited_by = None

        authors = OpenAlexClient._authors_from_work(w)

        return Paper(title=title, year=year, doi=doi, url=url, authors=authors, source="openalex", cited_by=cited_by)

    async def search_title(self, title: str, rows: int = 5) -> list[Paper]:
        q = (title or "").strip()
        if not q:
            return []
        params = {
            "search": q,
            "per-page": int(rows),
            "select": "title,doi,publication_year,authorships,primary_location,cited_by_count",
        }
        data = await self._get_json("/works", params=params)
        results = (data or {}).get("results") or []
        if not isinstance(results, list):
            return []
        out = []
        for w in results:
            if isinstance(w, dict):
                out.append(self._to_paper(w))
        return out

    async def lookup_doi(self, doi: str) -> Optional[Paper]:
        d = normalize_doi(doi).rstrip(").,;")
        if not d:
            return None
        # OpenAlex принимает внешний id как часть пути, он должен быть url-encoded
        ext = f"https://doi.org/{d}"
        path = "/works/" + quote(ext, safe="")
        data = await self._get_json(path, params={"select": "title,doi,publication_year,authorships,primary_location,cited_by_count"})
        if isinstance(data, dict) and data.get("id"):
            return self._to_paper(data)
        return None
