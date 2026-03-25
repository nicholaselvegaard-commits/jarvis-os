"""
NEXUS Web Scraper — henter informasjon fra prospects' nettsider.

Brukes til å generere personaliserte observasjoner for cold outreach.
Ingen Selenium/Playwright — kun requests + BeautifulSoup (rask og serverkompatibel).
"""

import re
import logging
import requests
from typing import Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 10


def scrape_website(url: str) -> dict:
    """
    Henter nøkkelinfo fra en bedrifts nettside.
    Returnerer: title, description, about, services, signals
    """
    if not url:
        return {}

    if not url.startswith("http"):
        url = f"https://{url}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Scraper: Kunne ikke nå {url}: {e}")
        return {}

    soup = BeautifulSoup(resp.text, "lxml")

    # Fjern script og style
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    result = {
        "url": url,
        "title": _get_title(soup),
        "description": _get_description(soup),
        "about": _get_about_text(soup),
        "signals": _detect_signals(soup, resp.text),
    }

    logger.info(f"Scraper: Hentet info fra {url} — {len(result.get('about', ''))} tegn")
    return result


def _get_title(soup: BeautifulSoup) -> str:
    tag = soup.find("title")
    return tag.get_text(strip=True)[:200] if tag else ""


def _get_description(soup: BeautifulSoup) -> str:
    for attr in [{"name": "description"}, {"property": "og:description"}]:
        tag = soup.find("meta", attrs=attr)
        if tag and tag.get("content"):
            return tag["content"][:300]
    return ""


def _get_about_text(soup: BeautifulSoup) -> str:
    """Finn den mest relevante teksten på siden — om-seksjoner, hero-tekst, etc."""
    candidates = []

    # Prøv om/about-seksjoner
    for selector in ["#om", "#about", ".about", ".om-oss", "section"]:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 50:
                candidates.append(text[:500])

    # Fallback: første lange paragraf
    if not candidates:
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if len(text) > 80:
                candidates.append(text[:400])
                break

    return candidates[0] if candidates else ""


def _detect_signals(soup: BeautifulSoup, raw_html: str) -> list:
    """
    Oppdager signaler som indikerer AI-modenhet og smertepunkter.
    Returnerer en liste med relevante observasjoner til pitchen.
    """
    signals = []
    text_lower = soup.get_text().lower()
    html_lower = raw_html.lower()

    # Tegn på manuell drift (salgsmulighet)
    manual_keywords = ["kontakt oss", "ring oss", "send e-post", "bestill time", "book møte"]
    if any(k in text_lower for k in manual_keywords):
        signals.append("Manuell kontaktprosess — chatbot-kandidat")

    # Tegn på vekst (åpen for investering)
    growth_keywords = ["vi ansetter", "ledige stillinger", "join our team", "vi vokser"]
    if any(k in text_lower for k in growth_keywords):
        signals.append("Bedriften ansetter — skaleringsutfordringer")

    # Bruker allerede noen tech-verktøy
    if "hubspot" in html_lower or "pipedrive" in html_lower:
        signals.append("Bruker CRM — klar for AI-integrasjon")
    if "shopify" in html_lower or "woocommerce" in html_lower:
        signals.append("Har nettbutikk — AI produktanbefalinger aktuelt")
    if "wordpress" in html_lower:
        signals.append("WordPress-side — potensial for AI-chatbot")

    # Ingen AI nevnt (stor mulighet)
    ai_keywords = ["kunstig intelligens", "ai ", "artificial intelligence", "automatisering", "chatbot"]
    if not any(k in text_lower for k in ai_keywords):
        signals.append("Ingen AI i bruk ennå — stort potensial")

    return signals[:3]  # Maks 3 signaler


def build_observation(scraped: dict) -> str:
    """
    Bygger en personalisert observasjons-setning for cold email.
    Brukes som {observation} i COLD_EMAIL_TEMPLATE_NO.
    """
    if not scraped:
        return "Jeg studerte nettsiden deres og la merke til at dere har et profesjonelt oppsett."

    signals = scraped.get("signals", [])
    description = scraped.get("description", "")
    title = scraped.get("title", "")

    if signals:
        signal = signals[0]
        if "chatbot" in signal.lower():
            return f"Jeg la merke til at {title or 'dere'} håndterer kundekontakt manuelt — noe vi kan automatisere."
        if "ansetter" in signal.lower():
            return f"Jeg ser at {title or 'dere'} er i vekst — mange bedrifter i den fasen oppdager at AI kan erstatte 2-3 stillinger."
        if "CRM" in signal:
            return f"Jeg ser at dere bruker CRM — vi kan koble AI rett inn og automatisere lead-prosessen."
        if "nettbutikk" in signal.lower():
            return f"Jeg la merke til nettbutikken — vi har hjulpet lignende butikker med AI som øker konvertering 15-25%."

    if description:
        return f"Jeg studerte {title or 'nettsiden deres'} — {description[:100].rstrip('.')}."

    return f"Jeg studerte {title or 'nettsiden deres'} og ser tydelige muligheter for AI-automatisering."
