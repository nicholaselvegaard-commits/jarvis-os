"""
Finn.no scraper. Finds business leads, job postings, and properties.
Uses httpx + BeautifulSoup since Finn has no public API.
"""
import logging
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from tools.retry import with_retry

logger = logging.getLogger(__name__)

FINN_BASE = "https://www.finn.no"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "nb-NO,nb;q=0.9",
}


@dataclass
class FinnListing:
    title: str
    url: str
    price: str
    location: str
    published: str
    description: str


@with_retry()
def search_jobs(query: str, location: str = "Bodø", limit: int = 10) -> list[FinnListing]:
    """
    Search Finn.no job listings.

    Args:
        query: Job title or keywords
        location: City filter
        limit: Max results

    Returns:
        List of FinnListing
    """
    resp = httpx.get(
        f"{FINN_BASE}/job/fulltime/search.html",
        params={"q": query, "location": location},
        headers=HEADERS,
        timeout=15.0,
        follow_redirects=True,
    )
    return _parse_listings(resp.text, limit)


@with_retry()
def search_business_services(query: str = "bedrift tjenester", limit: int = 10) -> list[FinnListing]:
    """
    Search Finn.no for B2B service listings (potential leads wanting to buy services).
    """
    resp = httpx.get(
        f"{FINN_BASE}/tjenester/annet/search.html",
        params={"q": query},
        headers=HEADERS,
        timeout=15.0,
        follow_redirects=True,
    )
    return _parse_listings(resp.text, limit)


@with_retry()
def search_for_sale(query: str, limit: int = 10) -> list[FinnListing]:
    """Search Finn.no torget / for-sale listings."""
    resp = httpx.get(
        f"{FINN_BASE}/torget/forsale/search.html",
        params={"q": query},
        headers=HEADERS,
        timeout=15.0,
        follow_redirects=True,
    )
    return _parse_listings(resp.text, limit)


def _parse_listings(html: str, limit: int) -> list[FinnListing]:
    soup = BeautifulSoup(html, "html.parser")
    listings = []

    for article in soup.find_all("article", limit=limit):
        title_el = article.find(["h2", "h3"])
        link_el = article.find("a", href=True)
        price_el = article.find(class_=lambda c: c and "price" in c.lower() if c else False)
        loc_el = article.find(class_=lambda c: c and ("location" in c.lower() or "sted" in c.lower()) if c else False)

        title = title_el.get_text(strip=True) if title_el else ""
        url = FINN_BASE + link_el["href"] if link_el and link_el["href"].startswith("/") else (link_el["href"] if link_el else "")
        price = price_el.get_text(strip=True) if price_el else ""
        location = loc_el.get_text(strip=True) if loc_el else ""

        if title:
            listings.append(FinnListing(
                title=title, url=url, price=price,
                location=location, published="", description=""
            ))

    logger.info(f"Finn.no: {len(listings)} listings")
    return listings
