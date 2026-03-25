"""
DuckDuckGo-søk — gratis, ingen API-nøkkel nødvendig.
Primær fallback når Brave/Perplexity ikke er tilgjengelig.

Prøver i rekkefølge:
1. duckduckgo-search Python-pakke (rask, strukturert)
2. DuckDuckGo Instant Answer JSON API (ingen pakke nødvendig)
3. DuckDuckGo HTML scrape (alltid fungerer)
"""
import logging
import re
import urllib.parse
import urllib.request
import json
from typing import Optional

logger = logging.getLogger(__name__)


def search(query: str, max_results: int = 5) -> str:
    """
    Søk på nettet via DuckDuckGo. Returnerer formatert tekst klar til å sende til LLM.
    Ingen API-nøkkel nødvendig.
    """
    # Prøv duckduckgo-search pakke først
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(f"**{r['title']}**\n{r['href']}\n{r['body']}")
        if results:
            logger.info(f"DDG pakke: {len(results)} resultater for '{query}'")
            return f"Søkeresultater for: {query}\n\n" + "\n\n".join(results)
    except Exception as e:
        logger.debug(f"duckduckgo-search pakke ikke tilgjengelig: {e}")

    # Fallback: DuckDuckGo Instant Answer API
    try:
        result = _ddg_instant(query)
        if result:
            return result
    except Exception as e:
        logger.debug(f"DDG instant answer feilet: {e}")

    # Siste fallback: HTML scrape
    try:
        return _ddg_html_scrape(query, max_results)
    except Exception as e:
        logger.error(f"Alle DDG-metoder feilet: {e}")
        return f"Søk feilet for: {query}"


def _ddg_instant(query: str) -> Optional[str]:
    """DuckDuckGo Instant Answer API — gir svar uten web-resultater."""
    url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    parts = []
    if data.get("AbstractText"):
        parts.append(data["AbstractText"])
    if data.get("Answer"):
        parts.append(f"Svar: {data['Answer']}")
    for r in data.get("RelatedTopics", [])[:3]:
        if isinstance(r, dict) and r.get("Text"):
            parts.append(f"• {r['Text'][:200]}")

    return "\n\n".join(parts) if parts else None


def _ddg_html_scrape(query: str, max_results: int) -> str:
    """Scraper DuckDuckGo HTML-resultater uten pakker."""
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "no,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    # Ekstraher titler og snippets med regex (unngår BeautifulSoup-avhengighet)
    titles = re.findall(r'class="result__title"[^>]*>.*?<a[^>]*>(.*?)</a>', html, re.DOTALL)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</span>', html, re.DOTALL)

    # Rens HTML-tags
    def strip_tags(s):
        return re.sub(r"<[^>]+>", "", s).strip()

    results = []
    for i in range(min(max_results, len(titles))):
        title = strip_tags(titles[i]) if i < len(titles) else ""
        snippet = strip_tags(snippets[i]) if i < len(snippets) else ""
        if title or snippet:
            results.append(f"**{title}**\n{snippet}")

    if not results:
        return f"Ingen resultater funnet for: {query}"

    return f"Søkeresultater for: {query}\n\n" + "\n\n".join(results)
