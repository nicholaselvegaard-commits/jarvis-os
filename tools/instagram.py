"""
Instagram integration — two modes:

1. Personal account (instagrapi — unofficial API):
   - post_photo(), post_reel(), get_profile(), get_recent_posts()
   - Requires: INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD
   - Works with personal accounts

2. Business account (Meta Graph API — official):
   - read_dm_inbox(), reply_to_dm(), get_insights()
   - Requires: INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_ACCOUNT_ID
   - Requires an Instagram Business/Creator account linked to a Facebook Page
   - Get a long-lived Page Access Token from Meta Developer Portal

Dependencies: instagrapi, httpx
"""
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from tools.retry import check_http_response, with_retry

load_dotenv()

logger = logging.getLogger(__name__)

SESSION_FILE = Path("memory/instagram_session.json")
GRAPH_BASE = "https://graph.facebook.com/v19.0"


# ──────────────────────────────────────────────
# Personal account — instagrapi (unofficial)
# ──────────────────────────────────────────────

_instagrapi_client = None  # Module-level singleton — login happens once per process


def _get_instagrapi_client():
    """Return the cached instagrapi Client, logging in once if needed."""
    global _instagrapi_client
    if _instagrapi_client is not None:
        return _instagrapi_client

    try:
        from instagrapi import Client
    except ImportError:
        raise ImportError("Install instagrapi: pip install instagrapi")

    username = os.getenv("INSTAGRAM_USERNAME")
    password = os.getenv("INSTAGRAM_PASSWORD")
    if not username or not password:
        raise ValueError("INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD must be set in .env")

    cl = Client()

    if SESSION_FILE.exists():
        try:
            cl.load_settings(SESSION_FILE)
            cl.login(username, password)
            logger.info("Instagram: logged in from cached session")
            _instagrapi_client = cl
            return cl
        except Exception as e:
            logger.warning(f"Instagram: cached session invalid ({e}), fresh login")

    cl.login(username, password)
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    cl.dump_settings(SESSION_FILE)
    logger.info(f"Instagram: logged in as @{username}")
    _instagrapi_client = cl
    return cl


@with_retry()
def post_photo(image_path: str, caption: str) -> dict:
    """
    Post a photo to Instagram (personal account via instagrapi).

    Args:
        image_path: Local path to JPEG or PNG
        caption: Caption including hashtags

    Returns:
        Dict: id, code, url
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    cl = _get_instagrapi_client()
    media = cl.photo_upload(path, caption)
    url = f"https://www.instagram.com/p/{media.code}/"
    logger.info(f"Instagram: photo posted — {url}")
    return {"id": str(media.pk), "code": media.code, "url": url}


@with_retry()
def post_reel(video_path: str, caption: str, thumbnail_path: str = "") -> dict:
    """
    Post a reel (video) to Instagram (personal account via instagrapi).

    Args:
        video_path: Local path to .mp4
        caption: Caption
        thumbnail_path: Optional thumbnail image path

    Returns:
        Dict: id, code, url
    """
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    thumb = Path(thumbnail_path) if thumbnail_path else None
    if thumb and not thumb.exists():
        raise FileNotFoundError(f"Thumbnail not found: {thumbnail_path}")

    cl = _get_instagrapi_client()
    media = cl.clip_upload(path, caption, thumbnail=thumb)
    url = f"https://www.instagram.com/p/{media.code}/"
    logger.info(f"Instagram: reel posted — {url}")
    return {"id": str(media.pk), "code": media.code, "url": url}


@with_retry()
def get_profile() -> dict:
    """
    Get profile info for the authenticated personal account.

    Returns:
        Dict: username, full_name, followers, following, posts, biography
    """
    cl = _get_instagrapi_client()
    user = cl.account_info()
    return {
        "username": user.username,
        "full_name": user.full_name,
        "followers": user.follower_count,
        "following": user.following_count,
        "posts": user.media_count,
        "biography": user.biography,
    }


@with_retry()
def get_recent_posts(count: int = 5) -> list[dict]:
    """
    Get recent posts from the personal account.

    Args:
        count: Number of posts (default 5)

    Returns:
        List of dicts: id, url, caption, like_count, comment_count, timestamp
    """
    cl = _get_instagrapi_client()
    medias = cl.user_medias(cl.user_id, amount=count)
    return [
        {
            "id": str(m.pk),
            "url": f"https://www.instagram.com/p/{m.code}/",
            "caption": (m.caption_text or "")[:200],
            "like_count": m.like_count,
            "comment_count": m.comment_count,
            "timestamp": m.taken_at.isoformat() if m.taken_at else "",
        }
        for m in medias
    ]


# ──────────────────────────────────────────────
# Business account — Meta Graph API (official)
# ──────────────────────────────────────────────

def _meta_headers() -> dict:
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        raise ValueError("INSTAGRAM_ACCESS_TOKEN must be set in .env (long-lived Page Access Token)")
    return {"Authorization": f"Bearer {token}"}


def _account_id() -> str:
    acct = os.getenv("INSTAGRAM_ACCOUNT_ID")
    if not acct:
        raise ValueError("INSTAGRAM_ACCOUNT_ID must be set in .env (Instagram Business Account ID)")
    return acct


@with_retry()
def read_dm_inbox(limit: int = 10) -> list[dict]:
    """
    Read recent Instagram DM conversations (Business/Creator account only).

    Requires INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID in .env.

    Args:
        limit: Max number of conversations to return (default 10)

    Returns:
        List of dicts: id, participants, snippet, updated_time
    """
    acct_id = _account_id()
    resp = httpx.get(
        f"{GRAPH_BASE}/{acct_id}/conversations",
        headers=_meta_headers(),
        params={"platform": "instagram", "fields": "id,participants,snippet,updated_time", "limit": limit},
        timeout=30,
    )
    check_http_response(resp, "read_dm_inbox")

    conversations = [
        {
            "id": conv["id"],
            "participants": [p.get("name", p.get("id", "?")) for p in conv.get("participants", {}).get("data", [])],
            "snippet": conv.get("snippet", ""),
            "updated_time": conv.get("updated_time", ""),
        }
        for conv in resp.json().get("data", [])
    ]
    logger.info(f"Instagram: fetched {len(conversations)} DM conversations")
    return conversations


@with_retry()
def reply_to_dm(conversation_id: str, message: str) -> dict:
    """
    Reply to an Instagram DM conversation (Business/Creator account only).

    Args:
        conversation_id: Conversation ID from read_dm_inbox()
        message: Text message to send

    Returns:
        Dict: message_id
    """
    acct_id = _account_id()
    resp = httpx.post(
        f"{GRAPH_BASE}/{acct_id}/messages",
        headers=_meta_headers(),
        json={"recipient": {"conversation_id": conversation_id}, "message": {"text": message}},
        timeout=30,
    )
    check_http_response(resp, "reply_to_dm", ok=(200, 201))

    data = resp.json()
    logger.info(f"Instagram: DM reply sent to conversation {conversation_id}")
    return {"message_id": data.get("message_id", data.get("id", ""))}


@with_retry()
def get_insights(metric: str = "impressions,reach,profile_views", period: str = "day") -> list[dict]:
    """
    Get Instagram Business account insights.

    Args:
        metric: Comma-separated metrics — e.g. 'impressions,reach,profile_views,follower_count'
        period: 'day', 'week', or 'days_28'

    Returns:
        List of dicts: name, period, values, title
    """
    acct_id = _account_id()
    resp = httpx.get(
        f"{GRAPH_BASE}/{acct_id}/insights",
        headers=_meta_headers(),
        params={"metric": metric, "period": period},
        timeout=30,
    )
    check_http_response(resp, "get_insights")

    insights = resp.json().get("data", [])
    logger.info(f"Instagram: fetched {len(insights)} insight metrics")
    return [
        {
            "name": item.get("name"),
            "period": item.get("period"),
            "values": item.get("values", []),
            "title": item.get("title", ""),
        }
        for item in insights
    ]
