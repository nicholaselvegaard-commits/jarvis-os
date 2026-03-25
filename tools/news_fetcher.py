"""
News aggregator. Fetches from NewsAPI, Google News RSS, and Norsk media.
Used by morning report and news_agent.
"""
import logging
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published: str
    summary: str


RSS_FEEDS = {
    "NRK":       "https://www.nrk.no/nyheter/siste.rss",
    "E24":        "https://e24.no/rss/",
    "DN":         "https://www.dn.no/rss",
    "TechCrunch": "https://techcrunch.com/feed/",
    "HN":         "https://hnrss.org/frontpage",
}


@with_retry()
def fetch_rss(feed_url: str, source_name: str, limit: int = 5) -> list[NewsItem]:
    """Fetch articles from an RSS feed."""
    resp = httpx.get(feed_url, timeout=10.0, follow_redirects=True)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    items = []
    for item in root.iter("item"):
        if len(items) >= limit:
            break
        title = item.findtext("title", "").strip()
        url = item.findtext("link", "").strip()
        pub = item.findtext("pubDate", "").strip()
        summary = item.findtext("description", "").strip()[:300]
        if title and url:
            items.append(NewsItem(title=title, url=url, source=source_name, published=pub, summary=summary))
    return items


def fetch_all(limit_per_source: int = 5) -> list[NewsItem]:
    """Fetch from all configured RSS feeds. Returns combined list."""
    all_items = []
    for name, url in RSS_FEEDS.items():
        try:
            items = fetch_rss(url, name, limit_per_source)
            all_items.extend(items)
        except Exception as exc:
            logger.warning(f"Failed to fetch {name}: {exc}")
    logger.info(f"news_fetcher: {len(all_items)} articles from {len(RSS_FEEDS)} sources")
    return all_items


@with_retry()
def fetch_newsapi(query: str, limit: int = 5) -> list[NewsItem]:
    """Search NewsAPI for articles matching a query."""
    key = os.getenv("NEWSAPI_KEY", "")
    if not key:
        logger.warning("NEWSAPI_KEY not set — skipping NewsAPI")
        return []
    resp = httpx.get(
        "https://newsapi.org/v2/everything",
        params={"q": query, "pageSize": limit, "sortBy": "publishedAt", "language": "no,en"},
        headers={"X-Api-Key": key},
        timeout=10.0,
    )
    resp.raise_for_status()
    items = []
    for a in resp.json().get("articles", []):
        items.append(NewsItem(
            title=a.get("title", ""),
            url=a.get("url", ""),
            source=a.get("source", {}).get("name", ""),
            published=a.get("publishedAt", "")[:10],
            summary=a.get("description", "")[:300],
        ))
    return items


def format_briefing(items: list[NewsItem], max_items: int = 10) -> str:
    """Format news items as a Telegram-friendly message."""
    lines = [f"📰 *Nyheter* — {datetime.now(timezone.utc).strftime('%d.%m %H:%M')}"]
    for item in items[:max_items]:
        lines.append(f"\n*{item.source}*: [{item.title}]({item.url})")
    return "\n".join(lines)
