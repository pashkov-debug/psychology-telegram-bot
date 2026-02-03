from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp

CROSSREF_BASE = "https://api.crossref.org"


@dataclass(frozen=True)
class WorkItem:
    title: str
    year: Optional[int]
    doi: Optional[str]
    url: Optional[str]
    authors: str
    cited_by: Optional[int]


class CrossrefError(RuntimeError):
    pass


class CrossrefClient:
    def __init__(self, session: aiohttp.ClientSession, mailto: str = "", user_agent: str = "psych-bot/1.0"):
        self._session = session
        self._mailto = (mailto or "").strip()
        self._ua = user_agent or "psych-bot/1.0"

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{CROSSREF_BASE}{path}"
        if self._mailto:
            params = {**params, "mailto": self._mailto}

        headers = {"User-Agent": self._ua}

        try:
            async with self._session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as r:
                if r.status >= 400:
                    text = await r.text()
                    raise CrossrefError(f"Crossref HTTP {r.status}: {text[:300]}")
                return await r.json()
        except asyncio.TimeoutError as e:
            raise CrossrefError("Таймаут при обращении к Crossref.") from e
        except aiohttp.ClientError as e:
            raise CrossrefError("Сетевая ошибка при обращении к Crossref.") from e

    @staticmethod
    def _safe_first(lst: Any) -> str:
        if isinstance(lst, list) and lst:
            v = lst[0]
            return str(v).strip()
        return ""

    @staticmethod
    def _year_from_message(msg: dict[str, Any]) -> Optional[int]:
        for key in ("issued", "published-online", "published-print", "created"):
            dp = msg.get(key, {})
            parts = dp.get("date-parts")
            if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
                y = parts[0][0]
                if isinstance(y, int):
                    return y
        return None

    @staticmethod
    def _authors_from_message(msg: dict[str, Any]) -> str:
        authors = msg.get("author") or []
        if not isinstance(authors, list) or not authors:
            return ""
        names = []
        for a in authors[:4]:
            given = (a.get("given") or "").strip()
            family = (a.get("family") or "").strip()
            full = " ".join([p for p in (given, family) if p])
            if full:
                names.append(full)
        tail = " и др." if len(authors) > 4 else ""
        return ", ".join(names) + tail

    def _parse_items(self, data: dict[str, Any]) -> list[WorkItem]:
        msg = data.get("message") or {}
        items = msg.get("items") or []
        if not isinstance(items, list):
            return []
        out: list[WorkItem] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            title = self._safe_first(it.get("title"))
            doi = (it.get("DOI") or "").strip() or None
            url = (it.get("URL") or "").strip() or None
            year = self._year_from_message(it)
            authors = self._authors_from_message(it)
            cited_by = it.get("is-referenced-by-count")
            if not isinstance(cited_by, int):
                cited_by = None

            out.append(
                WorkItem(
                    title=title or "(без названия)",
                    year=year,
                    doi=doi,
                    url=url or (f"https://doi.org/{doi}" if doi else None),
                    authors=authors,
                    cited_by=cited_by,
                )
            )
        return out

    async def search(self, query: str, rows: int = 5) -> list[WorkItem]:
        params = {
            "query": query,
            "rows": rows,
            "filter": "type:journal-article",
            "select": "DOI,title,URL,author,issued,is-referenced-by-count",
        }
        data = await self._get_json("/works", params)
        return self._parse_items(data)

    async def search_by_author(self, author: str, rows: int = 5) -> list[WorkItem]:
        params = {
            "query.author": author,
            "rows": rows,
            "filter": "type:journal-article",
            "select": "DOI,title,URL,author,issued,is-referenced-by-count",
        }
        data = await self._get_json("/works", params)
        return self._parse_items(data)

    async def by_doi(self, doi: str) -> WorkItem:
        doi = doi.strip()
        if not doi:
            raise CrossrefError("Пустой DOI.")
        data = await self._get_json(
            f"/works/{doi}",
            params={"select": "DOI,title,URL,author,issued,is-referenced-by-count"},
        )
        msg = data.get("message") or {}
        items_data = {"message": {"items": [msg]}}
        items = self._parse_items(items_data)
        if not items:
            raise CrossrefError("Не удалось разобрать ответ Crossref.")
        return items[0]
