"""
LinkedIn API client for posting and lead generation.
Requires: LINKEDIN_ACCESS_TOKEN (OAuth2 — see LinkedIn Developer Portal)
"""
import logging
import os

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)

LINKEDIN_BASE = "https://api.linkedin.com/v2"


def _headers() -> dict:
    token = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
    if not token:
        raise ValueError("LINKEDIN_ACCESS_TOKEN not set in .env")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }


@with_retry()
def get_profile() -> dict:
    """Return the authenticated user's LinkedIn profile."""
    resp = httpx.get(
        f"{LINKEDIN_BASE}/me",
        headers=_headers(),
        params={"projection": "(id,localizedFirstName,localizedLastName,profilePicture)"},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


@with_retry()
def post_text(text: str) -> str:
    """
    Post a text update to LinkedIn.

    Args:
        text: Post content

    Returns:
        Post URN
    """
    profile = get_profile()
    author_urn = f"urn:li:person:{profile['id']}"

    resp = httpx.post(
        f"{LINKEDIN_BASE}/ugcPosts",
        headers=_headers(),
        json={
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    post_id = resp.headers.get("x-restli-id", "")
    logger.info(f"LinkedIn post published: {post_id}")
    return post_id


@with_retry()
def search_people(keywords: str, limit: int = 10) -> list[dict]:
    """
    Search LinkedIn for people (requires LinkedIn Sales Navigator or Partner API).
    Falls back to People Search API if available.
    """
    resp = httpx.get(
        f"{LINKEDIN_BASE}/search",
        headers=_headers(),
        params={"keywords": keywords, "count": limit, "q": "people"},
        timeout=15.0,
    )
    if resp.status_code == 403:
        logger.warning("LinkedIn People Search requires elevated API access")
        return []
    resp.raise_for_status()
    return resp.json().get("elements", [])
