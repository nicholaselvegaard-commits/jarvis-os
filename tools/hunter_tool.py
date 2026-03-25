"""
Hunter.io Tool — finn og verifiser e-poster til leads.

Løser problemet: Apollo.io finner leads men mangler e-post.
Hunter.io fyller gapet ved å finne verifiserte e-poster basert på
navn + domene eller bedriftsnavn.

Krev: HUNTER_API_KEY i .env
Skaff nøkkel: https://hunter.io (gratis: 25 søk/mnd, $49/mnd for 500/mnd)
"""

import os
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "")
HUNTER_BASE = "https://api.hunter.io/v2"


def find_email(first_name: str, last_name: str, domain: str) -> dict:
    """
    Finn e-postadressen til en person basert på navn + domene.

    Args:
        first_name: Fornavn
        last_name:  Etternavn
        domain:     Bedriftens domene (f.eks. "acme.no")

    Returns:
        {
          "email": "ola.hansen@acme.no",
          "score": 94,          # Konfidensgrad 0-100
          "verified": True,
          "sources": [...]
        }
    """
    if not HUNTER_API_KEY:
        logger.warning("HUNTER_API_KEY ikke satt")
        return {"email": None, "score": 0, "verified": False}

    params = {
        "first_name": first_name,
        "last_name": last_name,
        "domain": domain,
        "api_key": HUNTER_API_KEY,
    }

    try:
        resp = requests.get(f"{HUNTER_BASE}/email-finder", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return {
            "email": data.get("email"),
            "score": data.get("score", 0),
            "verified": data.get("score", 0) >= 70,
            "sources": data.get("sources", []),
        }
    except Exception as e:
        logger.error(f"Hunter find_email feil: {e}")
        return {"email": None, "score": 0, "verified": False}


def domain_search(domain: str, limit: int = 10) -> list[dict]:
    """
    Finn alle e-poster på et domene.
    Nyttig for å finne beslutningstakere på en bedrift.

    Args:
        domain: Bedriftens domene (f.eks. "acme.no")
        limit:  Maks antall resultater

    Returns:
        [{"email": "...", "first_name": "...", "last_name": "...", "title": "...", "confidence": 90}, ...]
    """
    if not HUNTER_API_KEY:
        return []

    params = {
        "domain": domain,
        "limit": limit,
        "api_key": HUNTER_API_KEY,
    }

    try:
        resp = requests.get(f"{HUNTER_BASE}/domain-search", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        emails = data.get("emails", [])
        return [
            {
                "email": e.get("value"),
                "first_name": e.get("first_name", ""),
                "last_name": e.get("last_name", ""),
                "title": e.get("position", ""),
                "confidence": e.get("confidence", 0),
                "verified": e.get("confidence", 0) >= 70,
            }
            for e in emails
            if e.get("value")
        ]
    except Exception as e:
        logger.error(f"Hunter domain_search feil: {e}")
        return []


def verify_email(email: str) -> dict:
    """
    Verifiser om en e-postadresse er gyldig og aktiv.
    Bruk dette FØR du sender e-post for å unngå bounce.

    Args:
        email: E-postadressen å verifisere

    Returns:
        {
          "valid": True,
          "status": "valid",   # "valid" | "invalid" | "accept_all" | "unknown"
          "score": 94
        }
    """
    if not HUNTER_API_KEY:
        return {"valid": True, "status": "unknown", "score": 50}

    params = {"email": email, "api_key": HUNTER_API_KEY}

    try:
        resp = requests.get(f"{HUNTER_BASE}/email-verifier", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        status = data.get("status", "unknown")
        return {
            "valid": status in ("valid", "accept_all"),
            "status": status,
            "score": data.get("score", 0),
        }
    except Exception as e:
        logger.error(f"Hunter verify_email feil: {e}")
        return {"valid": True, "status": "unknown", "score": 50}


def enrich_lead_email(lead: dict) -> dict:
    """
    Legg til eller verifiser e-post på et Apollo-lead.
    Brukes av research_agent når Apollo ikke har e-post.

    Args:
        lead: Lead-dict fra Apollo.io

    Returns:
        Oppdatert lead med "email" og "email_verified" felt
    """
    # Allerede har e-post — bare verifiser
    if lead.get("email"):
        result = verify_email(lead["email"])
        lead["email_verified"] = result["valid"]
        lead["email_score"] = result["score"]
        return lead

    # Prøv å finne e-post via domene
    website = lead.get("website", "")
    domain = website.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]

    if not domain:
        return lead

    first_name = lead.get("first_name", "")
    last_name = lead.get("last_name", "")

    if first_name and last_name:
        result = find_email(first_name, last_name, domain)
        if result.get("email") and result.get("verified"):
            lead["email"] = result["email"]
            lead["email_verified"] = True
            lead["email_score"] = result["score"]
            logger.info(f"Hunter: Fant e-post for {first_name} {last_name} @ {domain}")
    else:
        # Søk etter beslutningstakere på domenet
        emails = domain_search(domain, limit=3)
        if emails:
            best = max(emails, key=lambda x: x.get("confidence", 0))
            if best.get("confidence", 0) >= 70:
                lead["email"] = best["email"]
                lead["email_verified"] = True
                lead["email_score"] = best["confidence"]

    return lead
