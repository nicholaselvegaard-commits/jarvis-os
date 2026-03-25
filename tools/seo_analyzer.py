"""
SEO analyzer. Performs technical SEO audits for local businesses.
Used by seo_agent to generate reports and pitches.
"""
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from tools.retry import with_retry

logger = logging.getLogger(__name__)


@dataclass
class SEOAudit:
    url: str
    title: str
    meta_description: str
    h1_tags: list[str]
    h2_tags: list[str]
    word_count: int
    images_without_alt: int
    internal_links: int
    external_links: int
    has_canonical: bool
    has_robots_meta: bool
    has_og_tags: bool
    has_schema: bool
    page_size_kb: float
    issues: list[str] = field(default_factory=list)
    score: int = 0


@with_retry()
def audit(url: str) -> SEOAudit:
    """
    Perform a technical SEO audit of a URL.

    Args:
        url: Full URL to audit (include https://)

    Returns:
        SEOAudit with findings and score
    """
    if not url.startswith("http"):
        url = "https://" + url

    resp = httpx.get(
        url,
        headers={"User-Agent": "NicholasAI-SEOBot/1.0"},
        timeout=15.0,
        follow_redirects=True,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    domain = urlparse(url).netloc

    # Extract elements
    title = soup.title.string.strip() if soup.title else ""
    meta_desc = ""
    if meta := soup.find("meta", attrs={"name": "description"}):
        meta_desc = meta.get("content", "")

    h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1")]
    h2_tags = [h.get_text(strip=True) for h in soup.find_all("h2")][:5]
    word_count = len(soup.get_text().split())

    images = soup.find_all("img")
    images_without_alt = sum(1 for img in images if not img.get("alt"))

    links = soup.find_all("a", href=True)
    internal = sum(1 for a in links if domain in a["href"] or a["href"].startswith("/"))
    external = len(links) - internal

    has_canonical = bool(soup.find("link", rel="canonical"))
    has_robots = bool(soup.find("meta", attrs={"name": "robots"}))
    has_og = bool(soup.find("meta", property="og:title"))
    has_schema = bool(soup.find("script", type="application/ld+json"))
    page_size_kb = round(len(resp.content) / 1024, 1)

    # Score and issues
    issues = []
    score = 100

    if not title:
        issues.append("Missing page title"); score -= 15
    elif len(title) > 60:
        issues.append(f"Title too long ({len(title)} chars, max 60)"); score -= 5

    if not meta_desc:
        issues.append("Missing meta description"); score -= 10
    elif len(meta_desc) > 160:
        issues.append(f"Meta description too long ({len(meta_desc)} chars, max 160)"); score -= 3

    if not h1_tags:
        issues.append("Missing H1 tag"); score -= 10
    elif len(h1_tags) > 1:
        issues.append(f"Multiple H1 tags ({len(h1_tags)}) — should have exactly one"); score -= 5

    if images_without_alt > 0:
        issues.append(f"{images_without_alt} images missing alt text"); score -= min(images_without_alt * 2, 10)

    if not has_canonical:
        issues.append("No canonical URL tag"); score -= 5

    if not has_og:
        issues.append("Missing Open Graph tags (social sharing)"); score -= 5

    if not has_schema:
        issues.append("No structured data (schema.org)"); score -= 5

    if word_count < 300:
        issues.append(f"Low word count ({word_count}), aim for 300+ for indexed pages"); score -= 5

    if page_size_kb > 500:
        issues.append(f"Large page size ({page_size_kb}KB) — may affect Core Web Vitals"); score -= 5

    audit = SEOAudit(
        url=url, title=title, meta_description=meta_desc,
        h1_tags=h1_tags, h2_tags=h2_tags, word_count=word_count,
        images_without_alt=images_without_alt,
        internal_links=internal, external_links=external,
        has_canonical=has_canonical, has_robots_meta=has_robots,
        has_og_tags=has_og, has_schema=has_schema,
        page_size_kb=page_size_kb, issues=issues, score=max(score, 0),
    )
    logger.info(f"SEO audit {url}: score={audit.score}")
    return audit


def format_report(audit: SEOAudit) -> str:
    """Format SEO audit as a Telegram-friendly message."""
    lines = [
        f"*SEO Audit: {audit.url}*",
        f"Score: {audit.score}/100",
        f"",
        f"Title: {audit.title or '❌ Mangler'}",
        f"Meta: {audit.meta_description[:60] + '...' if len(audit.meta_description) > 60 else audit.meta_description or '❌ Mangler'}",
        f"H1: {audit.h1_tags[0][:50] if audit.h1_tags else '❌ Mangler'}",
        f"Ord: {audit.word_count} | Bilder u/alt: {audit.images_without_alt}",
        f"Schema: {'✅' if audit.has_schema else '❌'} | OG: {'✅' if audit.has_og_tags else '❌'}",
    ]
    if audit.issues:
        lines.append(f"\n*Problemer ({len(audit.issues)}):*")
        for issue in audit.issues[:5]:
            lines.append(f"• {issue}")
    return "\n".join(lines)
