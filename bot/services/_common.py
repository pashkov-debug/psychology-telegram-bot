
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import quote_plus


DOI_RE = re.compile(r"10\.[0-9]{4,9}/\S+", re.IGNORECASE)


def normalize_doi(raw: str) -> str:
    """Нормализует DOI: убирает префиксы вида https://doi.org/, doi: и пробелы."""
    s = (raw or "").strip()
    s = re.sub(r"^\s*(doi\s*:\s*)", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s, flags=re.IGNORECASE)
    return s.strip()


def looks_like_doi(raw: str) -> bool:
    s = normalize_doi(raw)
    # DOI может содержать ) . , в конце — аккуратно режем
    s = s.rstrip(").,;")
    return bool(DOI_RE.fullmatch(s) or DOI_RE.match(s))


def urlencode_query(s: str) -> str:
    return quote_plus((s or "").strip())


class RateLimiter:
    """Очень простой лимитер: гарантирует паузу min_interval сек между запросами."""

    def __init__(self, min_interval: float):
        self._min_interval = max(0.0, float(min_interval))
        self._lock = asyncio.Lock()
        self._last_ts = 0.0

    async def wait(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            delta = now - self._last_ts
            if delta < self._min_interval:
                await asyncio.sleep(self._min_interval - delta)
            self._last_ts = time.monotonic()


@dataclass(frozen=True)
class Paper:
    title: str
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    authors: str = ""
    source: str = ""  # e.g. "crossref", "pubmed", "openalex"
    cited_by: Optional[int] = None

    def key(self) -> str:
        if self.doi:
            return f"doi:{self.doi.lower()}"
        t = re.sub(r"\s+", " ", (self.title or "").strip().lower())
        return f"title:{t[:200]}"


class ProviderError(RuntimeError):
    """Ошибка конкретного провайдера."""
    pass
