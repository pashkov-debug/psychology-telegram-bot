from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from ._common import Paper, looks_like_doi, normalize_doi, ProviderError


class LiteratureError(RuntimeError):
    pass


@dataclass(frozen=True)
class Provider:
    name: str
    supports_title: bool
    supports_doi: bool

    # callables (duck-typing)
    client: object


class LiteratureService:
    """Агрегатор по нескольким открытым источникам."""

    def __init__(self, providers: Sequence[Provider]):
        self._providers = list(providers)

        # приоритеты для различных сценариев
        self._doi_order = [p for p in self._providers if p.supports_doi]
        self._title_order = [p for p in self._providers if p.supports_title]

    async def search(self, query: str, rows: int = 5) -> list[Paper]:
        """Поиск по DOI или названию статьи (авто-детект)."""
        q = (query or "").strip()
        if not q:
            return []

        if looks_like_doi(q):
            p = await self.lookup_doi(q)
            return [p] if p else []

        items = await self.search_title(q, rows=rows)
        return items[: int(rows)]

    async def search_title(self, title: str, rows: int = 5) -> list[Paper]:
        q = (title or "").strip()
        if not q:
            return []

        out: list[Paper] = []
        seen: set[str] = set()
        errors: list[str] = []

        for prov in self._title_order:
            try:
                # duck typing: у клиента должен быть метод search_title
                items = await prov.client.search_title(q, rows=rows)
            except ProviderError as e:
                errors.append(f"{prov.name}: {e}")
                continue
            except Exception as e:
                errors.append(f"{prov.name}: {e}")
                continue

            for it in items or []:
                if not isinstance(it, Paper):
                    continue
                k = it.key()
                if k in seen:
                    continue
                seen.add(k)
                out.append(it)
                if len(out) >= int(rows):
                    return out

        # Если ничего нет и при этом накопили ошибки — даём одну понятную ошибку наверх.
        if not out and errors:
            raise LiteratureError("Не удалось получить результаты (все источники вернули ошибки).")

        return out

    async def lookup_doi(self, doi: str) -> Optional[Paper]:
        d = normalize_doi(doi).rstrip(").,;")
        if not d:
            return None

        errors: list[str] = []
        for prov in self._doi_order:
            try:
                it = await prov.client.lookup_doi(d)
            except ProviderError as e:
                errors.append(f"{prov.name}: {e}")
                continue
            except Exception as e:
                errors.append(f"{prov.name}: {e}")
                continue

            if isinstance(it, Paper):
                # гарантируем нормализованный DOI
                if it.doi:
                    it = Paper(
                        title=it.title,
                        year=it.year,
                        doi=normalize_doi(it.doi).rstrip(").,;"),
                        url=it.url,
                        authors=it.authors,
                        source=it.source,
                        cited_by=it.cited_by,
                    )
                return it

        if errors:
            # не пробрасываем детали пользователю в чат, но runtime/лог может это распечатать
            raise LiteratureError("Не удалось получить метаданные по DOI (источники вернули ошибки).")

        return None
