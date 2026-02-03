from __future__ import annotations

import asyncio
from typing import Any, Optional

import aiohttp

from ._common import Paper, ProviderError, RateLimiter, normalize_doi

EUROPE_PMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"


class EuropePMCError(ProviderError):
    pass


class EuropePMCClient:
    def __init__(self, session: aiohttp.ClientSession, user_agent: str = "psych-bot/1.0"):
        self._session = session
        self._ua = user_agent or "psych-bot/1.0"
        # официального rps нет, но соблюдаем polite-паузу
        self._limiter = RateLimiter(min_interval=0.12)  # ~8 rps максимум

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        await self._limiter.wait()
        url = f"{EUROPE_PMC_BASE}{path}"
        headers = {"User-Agent": self._ua}
        try:
            async with self._session.get(
                url,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=14),
            ) as r:
                if r.status >= 400:
                    txt = await r.text()
                    raise EuropePMCError(f"Europe PMC HTTP {r.status}: {txt[:300]}")
                return await r.json()
        except asyncio.TimeoutError as e:
            raise EuropePMCError("Таймаут при обращении к Europe PMC.") from e
        except aiohttp.ClientError as e:
            raise EuropePMCError("Сетевая ошибка при обращении к Europe PMC.") from e

    @staticmethod
    def _to_paper(item: dict[str, Any]) -> Paper:
        title = (item.get("title") or "").strip() or "(без названия)"
        authors = (item.get("authorString") or "").strip()
        year = item.get("pubYear")
        if not isinstance(year, int):
            try:
                year = int(str(year)) if year else None
            except Exception:
                year = None

        doi = (item.get("doi") or "").strip() or None
        if doi:
            doi = normalize_doi(doi).rstrip(").,;")

        url = None
        if doi:
            url = f"https://doi.org/{doi}"
        else:
            # EuropePMC ID может быть PPR / PMCID / PMID и т.п.
            src = (item.get("source") or "").strip()
            _id = (item.get("id") or "").strip()
            if src and _id:
                url = f"https://europepmc.org/article/{src}/{_id}"

        return Paper(title=title, year=year, doi=doi, url=url, authors=authors, source="europepmc")

    async def search_title(self, title: str, rows: int = 5) -> list[Paper]:
        q = (title or "").strip()
        if not q:
            return []
        data = await self._get_json("/search", params={"query": f'TITLE:"{q}"', "format": "json", "pageSize": rows})
        results = (((data or {}).get("resultList") or {}).get("result")) or []
        if not isinstance(results, list):
            return []
        out: list[Paper] = []
        for it in results:
            if isinstance(it, dict):
                out.append(self._to_paper(it))
        return out

    async def lookup_doi(self, doi: str) -> Optional[Paper]:
        d = normalize_doi(doi).rstrip(").,;")
        if not d:
            return None
        data = await self._get_json("/search", params={"query": f"DOI:{d}", "format": "json", "pageSize": 1})
        results = (((data or {}).get("resultList") or {}).get("result")) or []
        if isinstance(results, list) and results:
            it = results[0]
            if isinstance(it, dict):
                return self._to_paper(it)
        return None
