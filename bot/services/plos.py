from __future__ import annotations

import asyncio
import re
from typing import Any, Optional

import aiohttp

from ._common import Paper, ProviderError, RateLimiter, normalize_doi

PLOS_BASE = "http://api.plos.org/search"


class PlosError(ProviderError):
    pass


_DOI_IN_ID = re.compile(r"^10\.[0-9]{4,9}/\S+$", re.IGNORECASE)


class PlosClient:
    def __init__(self, session: aiohttp.ClientSession, api_key: str = "", user_agent: str = "psych-bot/1.0"):
        self._session = session
        self._key = (api_key or "").strip()
        self._ua = user_agent or "psych-bot/1.0"
        self._limiter = RateLimiter(min_interval=0.2)

    async def _get_json(self, params: dict[str, Any]) -> dict[str, Any]:
        await self._limiter.wait()
        headers = {"User-Agent": self._ua}
        if self._key:
            params = {**params, "api_key": self._key}
        try:
            async with self._session.get(PLOS_BASE, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=16)) as r:
                if r.status >= 400:
                    txt = await r.text()
                    raise PlosError(f"PLOS HTTP {r.status}: {txt[:300]}")
                return await r.json()
        except asyncio.TimeoutError as e:
            raise PlosError("Таймаут при обращении к PLOS API.") from e
        except aiohttp.ClientError as e:
            raise PlosError("Сетевая ошибка при обращении к PLOS API.") from e

    @staticmethod
    def _authors(doc: dict[str, Any]) -> str:
        a = doc.get("author_display")
        if not isinstance(a, list) or not a:
            return ""
        names = []
        for x in a[:4]:
            s = str(x).strip()
            if s:
                names.append(s)
        tail = " и др." if len(a) > 4 else ""
        return ", ".join(names) + tail

    @staticmethod
    def _year(doc: dict[str, Any]) -> Optional[int]:
        d = str(doc.get("publication_date") or "").strip()
        if len(d) >= 4 and d[:4].isdigit():
            try:
                return int(d[:4])
            except Exception:
                return None
        return None

    @staticmethod
    def _doi(doc: dict[str, Any]) -> Optional[str]:
        # У PLOS поле "id" часто совпадает с DOI
        raw = (doc.get("id") or "").strip()
        if raw and _DOI_IN_ID.match(raw):
            return normalize_doi(raw).rstrip(").,;")
        # Иногда DOI может быть в "doi" (на всякий случай)
        raw2 = (doc.get("doi") or "").strip()
        if raw2 and _DOI_IN_ID.match(raw2):
            return normalize_doi(raw2).rstrip(").,;")
        return None

    @staticmethod
    def _title(doc: dict[str, Any]) -> str:
        t = doc.get("title_display")
        if isinstance(t, str) and t.strip():
            return t.strip()
        return "(без названия)"

    async def search_title(self, title: str, rows: int = 5) -> list[Paper]:
        q = (title or "").strip()
        if not q:
            return []
        data = await self._get_json(params={"q": f'title:"{q}"', "wt": "json", "rows": int(rows)})
        docs = (((data or {}).get("response") or {}).get("docs")) or []
        if not isinstance(docs, list):
            return []
        out: list[Paper] = []
        for d in docs:
            if not isinstance(d, dict):
                continue
            doi = self._doi(d)
            out.append(
                Paper(
                    title=self._title(d),
                    year=self._year(d),
                    doi=doi,
                    url=(f"https://doi.org/{doi}" if doi else None),
                    authors=self._authors(d),
                    source="plos",
                )
            )
        return out

    async def lookup_doi(self, doi: str) -> Optional[Paper]:
        d = normalize_doi(doi).rstrip(").,;")
        if not d:
            return None
        data = await self._get_json(params={"q": f'doi:"{d}"', "wt": "json", "rows": 1})
        docs = (((data or {}).get("response") or {}).get("docs")) or []
        if isinstance(docs, list) and docs:
            doc = docs[0]
            if isinstance(doc, dict):
                doi2 = self._doi(doc) or d
                return Paper(
                    title=self._title(doc),
                    year=self._year(doc),
                    doi=doi2,
                    url=f"https://doi.org/{doi2}",
                    authors=self._authors(doc),
                    source="plos",
                )
        return None
