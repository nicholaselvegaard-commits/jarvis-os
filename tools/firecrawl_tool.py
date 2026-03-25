"""
Firecrawl Tool — erstatter BeautifulSoup for webscraping.

Fordeler over BeautifulSoup:
- Scraper JS-renderte sider (React, Vue, etc.)
- Håndterer bot-blokkering automatisk
- Returnerer ren Markdown-tekst
- Kan scrape hele nettsteder med én kommando

Krev: FIRECRAWL_API_KEY i .env
Skaff nøkkel: https://firecrawl.dev (gratis tier: 500 sider/mnd)
"""

import os
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
FIRECRAWL_BASE = "https://api.firecrawl.dev/v1"


def scrape_url(url: str, formats: list = None) -> dict:
    """
    Skrap én URL og returner innhold som Markdown + metadata.

    Args:
        url:     Nettadressen å skrape
        formats: ["markdown", "html", "links"] — standard: markdown

    Returns:
        {
          "markdown": "# Tittel\n...",
          "title": "Side-tittel",
          "description": "Meta-beskrivelse",
          "links": [...],
          "error": None
        }
    """
    if not FIRECRAWL_API_KEY:
        logger.warning("FIRECRAWL_API_KEY ikke satt — bruker BeautifulSoup fallback")
        return _fallback_scrape(url)

    payload = {
        "url": url,
        "formats": formats or ["markdown"],
        "onlyMainContent": True,
        "timeout": 15000,
    }
    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(f"{FIRECRAWL_BASE}/scrape", json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("success"):
            logger.warning(f"Firecrawl mislyktes for {url}: {data.get('error')}")
            return _fallback_scrape(url)

        result = data.get("data", {})
        return {
            "markdown": result.get("markdown", ""),
            "title": result.get("metadata", {}).get("title", ""),
            "description": result.get("metadata", {}).get("description", ""),
            "links": result.get("links", []),
            "error": None,
        }
    except Exception as e:
        logger.error(f"Firecrawl feil for {url}: {e}")
        return _fallback_scrape(url)


def crawl_site(url: str, max_pages: int = 10) -> list[dict]:
    """
    Kravl hele nettstedet og returner alle sider som Markdown.
    Nyttig for å analysere bedrifters hele nettsted.

    Args:
        url:       Start-URL (f.eks. "https://bedrift.no")
        max_pages: Maks antall undersider (standard: 10)

    Returns:
        Liste med {url, markdown, title} per side
    """
    if not FIRECRAWL_API_KEY:
        return [scrape_url(url)]

    payload = {
        "url": url,
        "limit": max_pages,
        "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True},
    }
    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        # Start crawl-jobb
        resp = requests.post(f"{FIRECRAWL_BASE}/crawl", json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        job_id = resp.json().get("id")

        if not job_id:
            return [scrape_url(url)]

        # Poll for status
        import time
        for _ in range(20):
            time.sleep(3)
            status_resp = requests.get(
                f"{FIRECRAWL_BASE}/crawl/{job_id}",
                headers=headers,
                timeout=10,
            )
            data = status_resp.json()
            if data.get("status") == "completed":
                pages = data.get("data", [])
                return [
                    {
                        "url": p.get("metadata", {}).get("sourceURL", ""),
                        "markdown": p.get("markdown", ""),
                        "title": p.get("metadata", {}).get("title", ""),
                    }
                    for p in pages
                ]
            elif data.get("status") == "failed":
                break

        return [scrape_url(url)]
    except Exception as e:
        logger.error(f"Firecrawl crawl feil: {e}")
        return [scrape_url(url)]


def extract_lead_signals(url: str) -> dict:
    """
    Skrap bedriftens nettsted og ekstraher salgs-signaler.
    Brukes av research_agent for lead-scoring.

    Returns:
        {
          "observation": "Bedriften bruker manuell faktura...",
          "signals": ["hiring", "manual_process", "no_crm"],
          "description": "...",
          "title": "...",
        }
    """
    result = scrape_url(url)
    if result.get("error") or not result.get("markdown"):
        return {}

    text = result["markdown"].lower()

    signals = []
    signal_map = {
        "hiring":        ["vi ansetter", "stillinger", "karriere", "join our team", "ledige stillinger"],
        "manual_process":["manuell", "excel", "papir", "skjema", "kontakt oss for tilbud"],
        "no_crm":        ["ring oss", "send e-post", "kontaktskjema", "fyll ut skjema"],
        "growth":        ["vekst", "ekspanderer", "ny kontor", "øker kapasitet", "scale"],
        "no_ai":         ["vi er et tradisjonelt", "vi gjør alt manuelt", "uten automatisering"],
        "shopify":       ["shopify", "nettbutikk", "e-handel", "webshop"],
        "crm_user":      ["hubspot", "salesforce", "pipedrive", "crm-system"],
    }

    for signal_name, keywords in signal_map.items():
        if any(kw in text for kw in keywords):
            signals.append(signal_name)

    # Bygg observasjon til cold email
    observation_parts = []
    if "hiring" in signals:
        observation_parts.append("vokser og ansetter")
    if "manual_process" in signals:
        observation_parts.append("bruker manuelle prosesser")
    if "shopify" in signals:
        observation_parts.append("driver nettbutikk")
    if "no_crm" in signals:
        observation_parts.append("mangler CRM/automatisering")

    observation = (
        f"Jeg la merke til at dere {', '.join(observation_parts)}."
        if observation_parts
        else f"Jeg so på nettsiden deres — {result.get('description', '')[:100]}"
    )

    return {
        "observation": observation,
        "signals": signals,
        "description": result.get("description", ""),
        "title": result.get("title", ""),
    }


def _fallback_scrape(url: str) -> dict:
    """Fallback til enkel requests+BeautifulSoup hvis Firecrawl ikke er konfigurert."""
    try:
        from tools.scraper import scrape_website
        data = scrape_website(url) or {}
        return {
            "markdown": data.get("about_text", ""),
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "links": [],
            "error": None,
        }
    except Exception as e:
        return {"markdown": "", "title": "", "description": "", "links": [], "error": str(e)}
