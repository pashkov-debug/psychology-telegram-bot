from __future__ import annotations

import asyncio
import re
from typing import Any, Optional

import aiohttp

from ._common import Paper, ProviderError, RateLimiter, normalize_doi

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedError(ProviderError):
    pass


class PubMedClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str = "",
        user_agent: str = "psych-bot/1.0",
        tool: str = "psych-bot",
        email: str = "",
    ):
        self._session = session
        self._api_key = (api_key or "").strip()
        self._ua = user_agent or "psych-bot/1.0"
        self._tool = (tool or "psych-bot").strip()
        self._email = (email or "").strip()

        # Ненавязчивый лимит: без ключа ~3 rps, с ключом можно чаще.
        self._limiter = RateLimiter(min_interval=0.12 if self._api_key else 0.34)

    def _base_params(self) -> dict[str, Any]:
        p: dict[str, Any] = {"tool": self._tool}
        if self._email:
            p["email"] = self._email
        if self._api_key:
            p["api_key"] = self._api_key
        return p

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        await self._limiter.wait()
        url = f"{EUTILS_BASE}{path}"
        headers = {"User-Agent": self._ua}
        params = {**self._base_params(), **params}
        try:
            async with self._session.get(
                url,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=16),
            ) as r:
                if r.status >= 400:
                    txt = await r.text()
                    raise PubMedError(f"PubMed HTTP {r.status}: {txt[:300]}")
                return await r.json()
        except asyncio.TimeoutError as e:
            raise PubMedError("Таймаут при обращении к PubMed (E-utilities).") from e
        except aiohttp.ClientError as e:
            raise PubMedError("Сетевая ошибка при обращении к PubMed (E-utilities).") from e

    async def _esearch(self, term: str, rows: int = 5) -> list[str]:
        data = await self._get_json(
            "/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": term,
                "retmode": "json",
                "retmax": int(rows),
                "sort": "relevance",
            },
        )
        es = (data or {}).get("esearchresult") or {}
        ids = es.get("idlist") or []
        if not isinstance(ids, list):
            return []
        out = []
        for x in ids:
            s = str(x).strip()
            if s:
                out.append(s)
        return out

    async def _esummary(self, pmids: list[str]) -> list[Paper]:
        if not pmids:
            return []
        data = await self._get_json(
            "/esummary.fcgi",
            params={
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "json",
            },
        )
        res = (data or {}).get("result") or {}
        uids = res.get("uids") or []
        if not isinstance(uids, list):
            return []

        out: list[Paper] = []
        for uid in uids:
            obj = res.get(str(uid)) or {}
            if not isinstance(obj, dict):
                continue
            title = (obj.get("title") or "").strip() or "(без названия)"

            authors = obj.get("authors") or []
            names = []
            if isinstance(authors, list):
                for a in authors[:4]:
                    if isinstance(a, dict):
                        n = (a.get("name") or "").strip()
                        if n:
                            names.append(n)
            tail = " и др." if isinstance(authors, list) and len(authors) > 4 else ""
            authors_s = ", ".join(names) + tail

            pubdate = (obj.get("pubdate") or "").strip()
            year: Optional[int] = None
            m = re.search(r"(19\d{2}|20\d{2})", pubdate)
            if m:
                try:
                    year = int(m.group(1))
                except Exception:
                    year = None

            doi: Optional[str] = None
            for aid in (obj.get("articleids") or []):
                if isinstance(aid, dict) and (aid.get("idtype") or "").lower() == "doi":
                    v = (aid.get("value") or "").strip()
                    if v:
                        doi = normalize_doi(v).rstrip(").,;")
                        break

            url = f"https://pubmed.ncbi.nlm.nih.gov/{uid}/" if uid else None

            out.append(Paper(title=title, year=year, doi=doi, url=url, authors=authors_s, source="pubmed"))
        return out

    async def search_title(self, title: str, rows: int = 5) -> list[Paper]:
        q = (title or "").strip()
        if not q:
            return []
        pmids = await self._esearch(term=f"{q}[ti]", rows=rows)
        return await self._esummary(pmids)

    async def lookup_doi(self, doi: str) -> Optional[Paper]:
        d = normalize_doi(doi).rstrip(").,;")
        if not d:
            return None
        # По справке NCBI можно искать по [AID] (Article Identifier)
        pmids = await self._esearch(term=f"{d}[AID]", rows=1)
        items = await self._esummary(pmids)
        return items[0] if items else None
