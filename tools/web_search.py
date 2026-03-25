"""
Web search tool using the Brave Search API.
Get a free API key at: https://api.search.brave.com/
"""
import logging
import os
import time
from typing import Optional

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

logger = logging.getLogger(__name__)

BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"
MAX_RETRIES = 3
BACKOFF_BASE = 2


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str


def search(query: str, num_results: int = 6) -> list[SearchResult]:
    """
    Search the web using the Brave Search API.

    Args:
        query: Search query string.
        num_results: Number of results (max 20 on free tier).

    Returns:
        List of SearchResult objects.
    """
    api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    if not api_key:
        raise ValueError(
            "BRAVE_SEARCH_API_KEY not set in .env — "
            "get a free key at https://api.search.brave.com/"
        )

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {"q": query, "count": num_results, "search_lang": "nb"}

    logger.info(f"Searching: {query!r}")
    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(BRAVE_API_URL, headers=headers, params=params)
                response.raise_for_status()

            data = response.json()
            web_results = data.get("web", {}).get("results", [])
            results = [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("description", ""),
                )
                for r in web_results
            ]
            logger.info(f"Got {len(results)} results for: {query!r}")
            return results

        except httpx.HTTPStatusError as e:
            logger.error(f"Brave Search HTTP {e.response.status_code}: {e.response.text}")
            raise
        except httpx.RequestError as e:
            last_error = e
            if attempt < MAX_RETRIES:
                wait = BACKOFF_BASE ** attempt
                logger.warning(f"Search attempt {attempt} failed, retrying in {wait}s: {e}")
                time.sleep(wait)
            else:
                logger.error(f"Search failed after {MAX_RETRIES} attempts")
                raise

    raise RuntimeError(f"Search failed: {query}") from last_error
