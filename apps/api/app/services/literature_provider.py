"""Optional external literature discovery providers.

Providers only return candidates. They never receive a database session and
cannot write Platform Paper or Knowledge assets.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.config import config
from app.services.knowledge import normalize_doi


class LiteratureProvider(Protocol):
    async def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]: ...

    async def resolve_doi(self, doi: str) -> dict[str, Any] | None: ...


class ScholarLiteratureProvider:
    def __init__(self, base_url: str, api_token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token.strip()

    def _headers(self) -> dict[str, str]:
        return {"auth-token": self.api_token} if self.api_token else {}

    async def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.get(
                f"{self.base_url}/api/papers/",
                params={"q": query, "limit": limit, "offset": 0},
                headers=self._headers(),
            )
            response.raise_for_status()
        payload = response.json()
        return list(payload.get("items", []))

    async def resolve_doi(self, doi: str) -> dict[str, Any] | None:
        normalized = normalize_doi(doi)
        for candidate in await self.search(normalized, limit=10):
            try:
                candidate_doi = normalize_doi(str(candidate.get("doi") or ""))
            except ValueError:
                continue
            if candidate_doi != normalized:
                continue
            authors = candidate.get("authors") or []
            return {
                "doi": normalized,
                "title": candidate.get("title") or "",
                "abstract": candidate.get("abstract") or "",
                "publication_year": candidate.get("publish_year"),
                "authors": [
                    item.get("name", "") if isinstance(item, dict) else str(item)
                    for item in authors
                ],
                "venue": candidate.get("journal_name") or "",
                "metadata_source": "scholar",
            }
        return None


def get_literature_provider() -> LiteratureProvider | None:
    if config.LITERATURE_PROVIDER == "scholar" and config.SCHOLAR_BASE_URL.strip():
        return ScholarLiteratureProvider(
            config.SCHOLAR_BASE_URL,
            config.SCHOLAR_API_TOKEN,
        )
    return None
