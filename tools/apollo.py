"""
Apollo.io API — komplett integrasjon for NEXUS.

Base URL: https://api.apollo.io/api/v1
Auth: Authorization: Bearer YOUR_API_KEY
"""

import os
import httpx
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")
BASE = "https://api.apollo.io/api/v1"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {APOLLO_API_KEY}",
        "Content-Type": "application/json",
    }


def _post(endpoint: str, payload: dict) -> dict:
    if not APOLLO_API_KEY:
        logger.error("APOLLO_API_KEY mangler")
        return {"error": "APOLLO_API_KEY ikke satt"}
    try:
        r = httpx.post(f"{BASE}{endpoint}", json=payload, headers=_headers(), timeout=30)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Apollo POST {endpoint} HTTP {e.response.status_code}: {e.response.text[:200]}")
        return {"error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        logger.error(f"Apollo POST {endpoint} feil: {e}")
        return {"error": str(e)}


def _get(endpoint: str, params: dict = None) -> dict:
    if not APOLLO_API_KEY:
        logger.error("APOLLO_API_KEY mangler")
        return {"error": "APOLLO_API_KEY ikke satt"}
    try:
        r = httpx.get(f"{BASE}{endpoint}", params=params or {}, headers=_headers(), timeout=30)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Apollo GET {endpoint} HTTP {e.response.status_code}: {e.response.text[:200]}")
        return {"error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        logger.error(f"Apollo GET {endpoint} feil: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# SEARCH
# ---------------------------------------------------------------------------

def search_people(
    job_titles: List[str] = None,
    countries: List[str] = None,
    min_employees: int = 5,
    max_employees: int = 500,
    per_page: int = 50,
    page: int = 1,
) -> List[Dict]:
    """Søk etter personer (leads) i Apollo."""
    data = _post("/mixed_people/search", {
        "per_page": per_page,
        "page": page,
        "person_titles": job_titles or ["CEO", "Daglig leder", "Founder", "Administrerende direktør"],
        "person_locations": countries or ["Norway"],
        "organization_num_employees_ranges": [f"{min_employees},{max_employees}"],
        "contact_email_status": ["verified", "likely to engage"],
    })
    people = data.get("people", [])
    logger.info(f"Apollo search_people: {len(people)} resultater")
    return _normalize_people(people)


def search_companies(
    keywords: List[str] = None,
    countries: List[str] = None,
    min_employees: int = 5,
    max_employees: int = 500,
    per_page: int = 25,
) -> List[Dict]:
    """Søk etter bedrifter i Apollo."""
    data = _post("/mixed_companies/search", {
        "per_page": per_page,
        "organization_locations": countries or ["Norway"],
        "organization_num_employees_ranges": [f"{min_employees},{max_employees}"],
        "q_organization_keyword_tags": keywords or [],
    })
    orgs = data.get("organizations", [])
    logger.info(f"Apollo search_companies: {len(orgs)} resultater")
    return orgs


def search_news(query: str, per_page: int = 10) -> List[Dict]:
    """Søk etter nyhetsartikler om en bedrift eller bransje."""
    data = _post("/news_articles/search", {
        "q_keywords": query,
        "per_page": per_page,
    })
    return data.get("news_articles", [])


# ---------------------------------------------------------------------------
# ENRICHMENT
# ---------------------------------------------------------------------------

def enrich_person(email: str) -> Optional[Dict]:
    """Berik en person basert på e-postadresse."""
    data = _post("/people/match", {"email": email, "reveal_personal_emails": True})
    person = data.get("person")
    if person:
        return _normalize_people([person])[0]
    return None


def enrich_organization(domain: str) -> Optional[Dict]:
    """Berik en organisasjon basert på domene."""
    data = _get("/organizations/enrich", {"domain": domain})
    return data.get("organization")


def bulk_enrich_people(emails: List[str]) -> List[Dict]:
    """Berik flere personer på én gang (maks 10 per kall)."""
    details = [{"email": e} for e in emails[:10]]
    data = _post("/people/bulk_match", {"details": details, "reveal_personal_emails": True})
    return _normalize_people(data.get("matches", []))


# ---------------------------------------------------------------------------
# CONTACTS (CRM)
# ---------------------------------------------------------------------------

def create_contact(lead: Dict) -> Optional[str]:
    """Lagre et lead som kontakt i Apollo CRM. Returnerer contact_id."""
    data = _post("/contacts", {
        "first_name": lead.get("first_name", ""),
        "last_name": lead.get("last_name", ""),
        "email": lead.get("email", ""),
        "title": lead.get("title", ""),
        "organization_name": lead.get("company", ""),
        "phone": lead.get("phone", ""),
    })
    contact = data.get("contact", {})
    contact_id = contact.get("id")
    if contact_id:
        logger.info(f"Apollo: Kontakt opprettet — {lead.get('email')} (id: {contact_id})")
    return contact_id


def update_contact_stage(contact_ids: List[str], stage_id: str):
    """Oppdater status på kontakter (f.eks. 'møte booket', 'konvertert')."""
    _post("/contacts/update_stages", {
        "contact_ids": contact_ids,
        "contact_stage_id": stage_id,
    })


def search_contacts(email: str = None, name: str = None) -> List[Dict]:
    """Søk etter eksisterende kontakter i Apollo CRM."""
    payload = {}
    # email takes priority; name is fallback
    if email:
        payload["q_keywords"] = email
    elif name:
        payload["q_keywords"] = name
    data = _post("/contacts/search", payload)
    return data.get("contacts", [])


def list_contact_stages() -> List[Dict]:
    """Hent alle tilgjengelige kontaktstadier."""
    data = _get("/contact_stages")
    return data.get("contact_stages", [])


# ---------------------------------------------------------------------------
# SEQUENCES (e-postsekvenser)
# ---------------------------------------------------------------------------

def add_to_sequence(contact_ids: List[str], campaign_id: str):
    """Legg kontakter til en e-postsekvens i Apollo."""
    _post("/emailer_campaign/add_contact_ids", {
        "id": campaign_id,
        "contact_ids": contact_ids,
    })
    logger.info(f"Apollo: {len(contact_ids)} kontakter lagt til sekvens {campaign_id}")


def get_email_stats(campaign_id: str) -> Dict:
    """Hent statistikk for en e-postkampanje."""
    data = _get("/emailer_messages/check_stats", {"emailer_campaign_id": campaign_id})
    return data


# ---------------------------------------------------------------------------
# ACCOUNTS
# ---------------------------------------------------------------------------

def create_account(company_name: str, domain: str = "", phone: str = "") -> Optional[str]:
    """Opprett en bedriftskonto i Apollo CRM."""
    data = _post("/accounts", {
        "name": company_name,
        "domain": domain,
        "phone": phone,
    })
    account = data.get("account", {})
    return account.get("id")


# ---------------------------------------------------------------------------
# DEALS
# ---------------------------------------------------------------------------

def create_deal(name: str, account_id: str, value: float = 0) -> Optional[str]:
    """Opprett en deal i Apollo CRM."""
    data = _post("/opportunities", {
        "name": name,
        "account_id": account_id,
        "amount": value,
    })
    return data.get("opportunity", {}).get("id")


# ---------------------------------------------------------------------------
# UTILITY
# ---------------------------------------------------------------------------

def check_api_usage() -> Dict:
    """Sjekk API-bruk og rate limits."""
    data = _post("/auth/api_usage_stats", {})
    logger.info(f"Apollo API-bruk: {data}")
    return data


def get_50_norwegian_leads() -> List[Dict]:
    """Shorthand: hent 50 norske SMB-leads klar for outreach."""
    return search_people(
        job_titles=["CEO", "Daglig leder", "Administrerende direktør", "Founder", "Eier"],
        countries=["Norway"],
        min_employees=5,
        max_employees=200,
        per_page=50,
    )


def _normalize_people(people: List[Dict]) -> List[Dict]:
    leads = []
    for p in people:
        org = p.get("organization") or {}
        lead = {
            "id": p.get("id", ""),
            "first_name": p.get("first_name", ""),
            "last_name": p.get("last_name", ""),
            "email": p.get("email", ""),
            "title": p.get("title", ""),
            "company": org.get("name", ""),
            "company_size": org.get("num_employees", ""),
            "industry": org.get("industry", ""),
            "phone": (p.get("phone_numbers") or [{}])[0].get("raw_number", ""),
            "linkedin_url": p.get("linkedin_url", ""),
            "city": p.get("city", ""),
            "country": p.get("country", ""),
            "website": org.get("website_url", ""),
        }
        if lead["email"]:
            leads.append(lead)
    return leads
