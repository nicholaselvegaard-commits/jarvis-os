"""
Exa semantic search — finds relevant pages by meaning, not just keywords.
Great for research where exact keywords are unknown.
"""
import logging
import os
from dataclasses import dataclass

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)

EXA_BASE_URL = "https://api.exa.ai"


@dataclass
class ExaResult:
    title: str
    url: str
    snippet: str
    published_date: str


@with_retry()
def search(query: str, limit: int = 5, include_text: bool = True) -> list[ExaResult]:
    """
    Semantic search via Exa.

    Args:
        query: Natural language search query
        limit: Max results
        include_text: Include page text snippets

    Returns:
        List of ExaResult
    """
    key = os.getenv("EXA_API_KEY", "")
    if not key:
        raise ValueError("EXA_API_KEY not set in .env")

    resp = httpx.post(
        f"{EXA_BASE_URL}/search",
        headers={"x-api-key": key, "Content-Type": "application/json"},
        json={
            "query": query,
            "numResults": limit,
            "contents": {"text": {"maxCharacters": 500}} if include_text else {},
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    results = []
    for r in resp.json().get("results", []):
        results.append(ExaResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            snippet=r.get("text", "") or r.get("snippet", ""),
            published_date=r.get("publishedDate", ""),
        ))
    logger.info(f"Exa search '{query}': {len(results)} results")
    return results
