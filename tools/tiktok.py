"""
TikTok integration via TikTok for Developers APIs.

APIs used:
  - TikTok Display API  — read user stats and video list
  - TikTok Content Posting API — upload videos
  - TikTok Research API — read comments (requires Research API access)

Setup:
  1. Apply at https://developers.tiktok.com/
  2. Create an app → get Client Key and Client Secret
  3. Complete OAuth 2.0 flow manually in a browser:
       https://www.tiktok.com/v2/auth/authorize?
         client_key=YOUR_CLIENT_KEY
         &response_type=code
         &scope=user.info.basic,video.list,video.publish,video.upload
         &redirect_uri=YOUR_REDIRECT_URI
         &state=random_string
  4. Exchange the auth code for an access token (see docs/integrations.md)
  5. Set TIKTOK_ACCESS_TOKEN in .env (long-lived token)

Required env vars:
  TIKTOK_ACCESS_TOKEN  — OAuth 2.0 user access token

Dependencies: httpx (already in requirements.txt)
"""
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from tools.retry import check_http_response, with_retry

load_dotenv()

logger = logging.getLogger(__name__)

API_BASE = "https://open.tiktokapis.com/v2"


def _headers() -> dict:
    token = os.getenv("TIKTOK_ACCESS_TOKEN")
    if not token:
        raise ValueError("TIKTOK_ACCESS_TOKEN must be set in .env")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@with_retry()
def get_user_info() -> dict:
    """
    Get basic info about the authenticated TikTok user.

    Returns:
        Dict: open_id, display_name, avatar_url, follower_count, following_count,
              likes_count, video_count
    """
    resp = httpx.post(
        f"{API_BASE}/user/info/",
        headers=_headers(),
        json={"fields": ["open_id", "display_name", "avatar_url", "follower_count",
                         "following_count", "likes_count", "video_count"]},
        timeout=30,
    )
    check_http_response(resp, "get_user_info")

    data = resp.json().get("data", {}).get("user", {})
    logger.info(f"TikTok: fetched user info for {data.get('display_name')}")
    return data


@with_retry()
def list_videos(limit: int = 10) -> list[dict]:
    """
    List recent videos from the authenticated TikTok account.

    Args:
        limit: Max number of videos (default 10, max 20 per page)

    Returns:
        List of dicts: id, title, cover_image_url, share_url,
                       view_count, like_count, comment_count, share_count, duration
    """
    resp = httpx.post(
        f"{API_BASE}/video/list/",
        headers=_headers(),
        params={"fields": "id,title,cover_image_url,share_url,view_count,like_count,"
                          "comment_count,share_count,duration"},
        json={"max_count": min(limit, 20)},
        timeout=30,
    )
    check_http_response(resp, "list_videos")

    videos = resp.json().get("data", {}).get("videos", [])
    logger.info(f"TikTok: listed {len(videos)} videos")
    return videos


@with_retry()
def get_video_comments(video_id: str, limit: int = 20) -> list[dict]:
    """
    Fetch comments on a TikTok video.

    Note: Requires Research API access (apply separately at developers.tiktok.com).

    Args:
        video_id: TikTok video ID
        limit: Max number of comments (default 20)

    Returns:
        List of dicts: id, text, like_count, create_time, username
    """
    resp = httpx.post(
        f"{API_BASE}/research/video/comment/list/",
        headers=_headers(),
        json={"video_id": video_id, "max_count": min(limit, 100), "cursor": 0},
        timeout=30,
    )
    check_http_response(resp, "get_video_comments")

    comments = resp.json().get("data", {}).get("comments", [])
    logger.info(f"TikTok: fetched {len(comments)} comments for video {video_id}")
    return comments


@with_retry()
def upload_video(video_path: str, title: str, privacy: str = "SELF_ONLY") -> dict:
    """
    Upload a video to TikTok using the Content Posting API (file upload flow).

    The video goes through TikTok's review process before going live.

    Args:
        video_path: Local path to an .mp4 file (max 500 MB, max 10 min)
        title: Video caption / title (max 2200 chars)
        privacy: Privacy level — 'PUBLIC_TO_EVERYONE', 'MUTUAL_FOLLOW_FRIENDS',
                 'FOLLOWER_OF_CREATOR', or 'SELF_ONLY' (default, safe for testing)

    Returns:
        Dict: publish_id (use to check status), status
    """
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    file_size = path.stat().st_size

    # Step 1: Initialize upload
    init_resp = httpx.post(
        f"{API_BASE}/post/publish/video/init/",
        headers=_headers(),
        json={
            "post_info": {
                "title": title[:2200],
                "privacy_level": privacy,
                "disable_duet": False,
                "disable_stitch": False,
                "disable_comment": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,
                "total_chunk_count": 1,
            },
        },
        timeout=30,
    )
    check_http_response(init_resp, "upload_video init")

    init_data = init_resp.json().get("data", {})
    publish_id = init_data["publish_id"]
    upload_url = init_data["upload_url"]

    # Step 2: Stream file directly — avoids loading 500 MB into memory
    with path.open("rb") as f:
        upload_resp = httpx.put(
            upload_url,
            content=f,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(file_size),
                "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
            },
            timeout=300,
        )

    check_http_response(upload_resp, "upload_video PUT", ok=(200, 201, 206))

    logger.info(f"TikTok: video uploaded — publish_id={publish_id}")
    return {"publish_id": publish_id, "status": "upload_complete", "privacy": privacy}


@with_retry()
def check_upload_status(publish_id: str) -> dict:
    """
    Check the processing status of an uploaded video.

    Args:
        publish_id: From upload_video()

    Returns:
        Dict: publish_id, status (e.g. 'PROCESSING_UPLOAD', 'SEND_TO_USER_INBOX', 'PUBLISH_COMPLETE')
    """
    resp = httpx.post(
        f"{API_BASE}/post/publish/status/fetch/",
        headers=_headers(),
        json={"publish_id": publish_id},
        timeout=30,
    )
    check_http_response(resp, "check_upload_status")

    data = resp.json().get("data", {})
    logger.info(f"TikTok: publish status for {publish_id}: {data.get('status')}")
    return {"publish_id": publish_id, "status": data.get("status", "unknown")}
