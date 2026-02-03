from __future__ import annotations

from dataclasses import dataclass

import aiohttp

from .crossref import CrossrefClient
from .pubmed import PubMedClient
from .europe_pmc import EuropePMCClient
from .openalex import OpenAlexClient
from .semanticscholar import SemanticScholarClient
from .doaj import DoajClient
from .plos import PlosClient
from .osf import OsfPreprintsClient
from .biorxiv import BiorxivClient
from .literature import LiteratureService, Provider


@dataclass(frozen=True)
class Services:
    # «прямые» клиенты (можно использовать точечно)
    crossref: CrossrefClient
    pubmed: PubMedClient
    europe_pmc: EuropePMCClient
    openalex: OpenAlexClient
    semanticscholar: SemanticScholarClient
    doaj: DoajClient
    plos: PlosClient
    osf: OsfPreprintsClient
    biorxiv: BiorxivClient
    medrxiv: BiorxivClient

    # агрегатор «поиск по DOI или названию»
    literature: LiteratureService


def init_services(
    session: aiohttp.ClientSession,
    *,
    user_agent: str = "psych-bot/1.0",
    # Полезные «polite» параметры
    mailto: str = "",
    # Ключи/параметры по источникам
    ncbi_api_key: str = "",
    ncbi_email: str = "",
    ncbi_tool: str = "psych-bot",
    plos_api_key: str = "",
    semanticscholar_api_key: str = "",
    doaj_api_key: str = "",
    osf_provider: str = "psyarxiv",
) -> Services:
    """
    Создаёт все клиенты внешних API и агрегатор.

    Порядок в агрегаторе выбран так, чтобы:
    - DOI lookup был максимально надёжным (Crossref/OpenAlex/S2),
    - title-search был быстрым и «широким» по покрытию.
    """

    crossref = CrossrefClient(session=session, mailto=mailto, user_agent=user_agent)
    pubmed = PubMedClient(session=session, api_key=ncbi_api_key, user_agent=user_agent, tool=ncbi_tool, email=ncbi_email)
    europe_pmc = EuropePMCClient(session=session, user_agent=user_agent)
    openalex = OpenAlexClient(session=session, mailto=mailto, user_agent=user_agent)
    semanticscholar = SemanticScholarClient(session=session, api_key=semanticscholar_api_key, user_agent=user_agent)
    doaj = DoajClient(session=session, api_key=doaj_api_key, user_agent=user_agent)
    plos = PlosClient(session=session, api_key=plos_api_key, user_agent=user_agent)
    osf = OsfPreprintsClient(session=session, user_agent=user_agent, provider=osf_provider)
    biorxiv = BiorxivClient(session=session, user_agent=user_agent, server="biorxiv")
    medrxiv = BiorxivClient(session=session, user_agent=user_agent, server="medrxiv")

    literature = LiteratureService(
        providers=[
            # Title search priority (supports_title=True)
            Provider(name="crossref", supports_title=True, supports_doi=True, client=crossref),
            Provider(name="openalex", supports_title=True, supports_doi=True, client=openalex),
            Provider(name="semanticscholar", supports_title=True, supports_doi=True, client=semanticscholar),
            Provider(name="europepmc", supports_title=True, supports_doi=True, client=europe_pmc),
            Provider(name="pubmed", supports_title=True, supports_doi=True, client=pubmed),
            Provider(name="plos", supports_title=True, supports_doi=True, client=plos),
            Provider(name="osf", supports_title=True, supports_doi=True, client=osf),
            Provider(name="doaj", supports_title=True, supports_doi=True, client=doaj),
            # DOI-only «дозапрос» для препринтов
            Provider(name="medrxiv", supports_title=False, supports_doi=True, client=medrxiv),
            Provider(name="biorxiv", supports_title=False, supports_doi=True, client=biorxiv),
        ]
    )

    return Services(
        crossref=crossref,
        pubmed=pubmed,
        europe_pmc=europe_pmc,
        openalex=openalex,
        semanticscholar=semanticscholar,
        doaj=doaj,
        plos=plos,
        osf=osf,
        biorxiv=biorxiv,
        medrxiv=medrxiv,
        literature=literature,
    )


__all__ = [
    "Services",
    "init_services",
    "LiteratureService",
]
