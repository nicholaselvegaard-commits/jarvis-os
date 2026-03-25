"""
Tavily research search — optimized for AI agents, returns structured summaries.
Best for deep research tasks.
"""
import logging
import os
from dataclasses import dataclass

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)


@dataclass
class TavilyResult:
    title: str
    url: str
    content: str
    score: float


@with_retry()
def search(query: str, limit: int = 5, search_depth: str = "basic") -> list[TavilyResult]:
    """
    Research search via Tavily.

    Args:
        query: Search query
        limit: Max results (1-10)
        search_depth: 'basic' or 'advanced' (advanced costs more credits)

    Returns:
        List of TavilyResult with full content
    """
    key = os.getenv("TAVILY_API_KEY", "")
    if not key:
        raise ValueError("TAVILY_API_KEY not set in .env")

    resp = httpx.post(
        "https://api.tavily.com/search",
        json={
            "api_key": key,
            "query": query,
            "max_results": limit,
            "search_depth": search_depth,
            "include_answer": True,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    results = []
    for r in data.get("results", []):
        results.append(TavilyResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            content=r.get("content", "")[:1000],
            score=r.get("score", 0.0),
        ))
    logger.info(f"Tavily '{query}': {len(results)} results")
    return results


@with_retry()
def get_answer(query: str) -> str:
    """Get a direct answer to a question using Tavily's answer mode."""
    key = os.getenv("TAVILY_API_KEY", "")
    if not key:
        raise ValueError("TAVILY_API_KEY not set in .env")
    resp = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": key, "query": query, "max_results": 3, "include_answer": True},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json().get("answer", "")
