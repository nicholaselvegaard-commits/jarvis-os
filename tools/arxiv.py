"""
ArXiv paper search and download.
Used by the nightly learning loop to update knowledge/tech.md.
"""
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)

ARXIV_BASE_URL = "http://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


@dataclass
class ArxivPaper:
    id: str
    title: str
    authors: list[str]
    abstract: str
    published: str
    url: str
    categories: list[str]


@with_retry()
def search(
    query: str,
    max_results: int = 10,
    sort_by: str = "submittedDate",
    categories: list[str] | None = None,
) -> list[ArxivPaper]:
    """
    Search ArXiv for papers.

    Args:
        query: Search query (supports field prefixes: ti:, abs:, au:)
        max_results: Max papers to return
        sort_by: 'submittedDate' or 'relevance'
        categories: Filter by ArXiv category (e.g. ['cs.AI', 'gr-qc'])

    Returns:
        List of ArxivPaper
    """
    search_query = query
    if categories:
        cat_filter = " OR ".join(f"cat:{c}" for c in categories)
        search_query = f"({query}) AND ({cat_filter})"

    params = {
        "search_query": search_query,
        "max_results": max_results,
        "sortBy": sort_by,
        "sortOrder": "descending",
    }

    resp = httpx.get(ARXIV_BASE_URL, params=params, timeout=30.0)
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    papers = []

    for entry in root.findall("atom:entry", NS):
        arxiv_id = (entry.findtext("atom:id", "", NS) or "").split("/abs/")[-1]
        title = (entry.findtext("atom:title", "", NS) or "").strip().replace("\n", " ")
        abstract = (entry.findtext("atom:summary", "", NS) or "").strip()[:600]
        published = entry.findtext("atom:published", "", NS) or ""
        authors = [
            a.findtext("atom:name", "", NS)
            for a in entry.findall("atom:author", NS)
        ]
        categories = [
            t.get("term", "")
            for t in entry.findall("atom:category", NS)
        ]
        url = f"https://arxiv.org/abs/{arxiv_id}"
        papers.append(ArxivPaper(
            id=arxiv_id,
            title=title,
            authors=authors[:3],
            abstract=abstract,
            published=published[:10],
            url=url,
            categories=categories,
        ))

    logger.info(f"ArXiv '{query}': {len(papers)} papers")
    return papers


def format_for_knowledge(papers: list[ArxivPaper]) -> str:
    """Format papers as Markdown for appending to knowledge files."""
    lines = []
    for p in papers:
        lines.append(f"### {p.title}")
        lines.append(f"**Authors**: {', '.join(p.authors)}")
        lines.append(f"**Published**: {p.published} | [Link]({p.url})")
        lines.append(f"**Abstract**: {p.abstract}")
        lines.append("")
    return "\n".join(lines)
