"""
Reddit API client. Monitor subreddits for leads and opportunities.
Uses Reddit's official API (OAuth2).
Requires: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD
"""
import logging
import os
import time
from dataclasses import dataclass

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)

REDDIT_BASE = "https://oauth.reddit.com"
_token_cache: dict = {"token": "", "expires_at": 0.0}


@dataclass
class RedditPost:
    id: str
    title: str
    url: str
    subreddit: str
    author: str
    score: int
    num_comments: int
    selftext: str
    created_utc: float


def _get_token() -> str:
    if time.monotonic() < _token_cache["expires_at"] and _token_cache["token"]:
        return _token_cache["token"]

    resp = httpx.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(os.getenv("REDDIT_CLIENT_ID", ""), os.getenv("REDDIT_CLIENT_SECRET", "")),
        data={
            "grant_type": "password",
            "username": os.getenv("REDDIT_USERNAME", ""),
            "password": os.getenv("REDDIT_PASSWORD", ""),
        },
        headers={"User-Agent": "NicholasAgent/1.0"},
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = time.monotonic() + data.get("expires_in", 3600) - 60
    return _token_cache["token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}", "User-Agent": "NicholasAgent/1.0"}


@with_retry()
def search(query: str, subreddit: str = "all", limit: int = 10, sort: str = "relevance") -> list[RedditPost]:
    """
    Search Reddit posts.

    Args:
        query: Search query
        subreddit: Subreddit to search in ('all' for everything)
        limit: Max results
        sort: 'relevance', 'hot', 'new', 'top'

    Returns:
        List of RedditPost
    """
    resp = httpx.get(
        f"{REDDIT_BASE}/r/{subreddit}/search",
        headers=_headers(),
        params={"q": query, "limit": limit, "sort": sort, "t": "week", "restrict_sr": subreddit != "all"},
        timeout=15.0,
    )
    resp.raise_for_status()
    return _parse_posts(resp.json())


@with_retry()
def get_hot(subreddit: str, limit: int = 10) -> list[RedditPost]:
    """Get hot posts from a subreddit."""
    resp = httpx.get(
        f"{REDDIT_BASE}/r/{subreddit}/hot",
        headers=_headers(),
        params={"limit": limit},
        timeout=15.0,
    )
    resp.raise_for_status()
    return _parse_posts(resp.json())


def _parse_posts(data: dict) -> list[RedditPost]:
    posts = []
    for child in data.get("data", {}).get("children", []):
        p = child["data"]
        posts.append(RedditPost(
            id=p["id"],
            title=p.get("title", ""),
            url=f"https://reddit.com{p.get('permalink', '')}",
            subreddit=p.get("subreddit", ""),
            author=p.get("author", ""),
            score=p.get("score", 0),
            num_comments=p.get("num_comments", 0),
            selftext=p.get("selftext", "")[:300],
            created_utc=p.get("created_utc", 0),
        ))
    return posts
