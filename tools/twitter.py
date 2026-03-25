"""
Twitter/X API v2 client via Tweepy.
Requires: TWITTER_API_KEY, TWITTER_API_SECRET,
          TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET,
          TWITTER_BEARER_TOKEN
"""
import logging
import os

import httpx

logger = logging.getLogger(__name__)

TWITTER_BASE = "https://api.twitter.com/2"


def _client():
    """Tweepy client for write operations (OAuth 1.0a)."""
    import tweepy
    return tweepy.Client(
        consumer_key=os.getenv("TWITTER_API_KEY"),
        consumer_secret=os.getenv("TWITTER_API_SECRET"),
        access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
        access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
        bearer_token=os.getenv("TWITTER_BEARER_TOKEN"),
        wait_on_rate_limit=False,
    )


def post_tweet(text: str) -> dict:
    """Post a tweet. Returns dict with tweet id and text."""
    if len(text) > 280:
        text = text[:277] + "..."
    client = _client()
    resp = client.create_tweet(text=text)
    tweet_id = resp.data["id"]
    logger.info(f"Tweet posted: {tweet_id}")
    return {"id": tweet_id, "text": text}


def search_recent(query: str, limit: int = 10) -> list[dict]:
    """Search recent tweets (last 7 days, free tier)."""
    client = _client()
    resp = client.search_recent_tweets(
        query=query,
        max_results=min(max(limit, 10), 100),
        tweet_fields=["created_at", "public_metrics", "author_id"],
    )
    if not resp.data:
        return []
    return [{"id": t.id, "text": t.text} for t in resp.data]


def get_my_tweets(limit: int = 10) -> list[dict]:
    """Get recent tweets from own account."""
    client = _client()
    me = client.get_me()
    resp = client.get_users_tweets(
        id=me.data.id,
        max_results=min(limit, 100),
        tweet_fields=["created_at", "public_metrics"],
    )
    if not resp.data:
        return []
    return [{"id": t.id, "text": t.text} for t in resp.data]
