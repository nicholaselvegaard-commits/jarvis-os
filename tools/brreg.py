"""
Brønnøysundregistrene API — gratis, åpent, ingen API-key.

Finn norske AS med antall ansatte, bransje, kommune.
Base URL: https://data.brreg.no/enhetsregisteret/api
"""
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BASE = "https://data.brreg.no/enhetsregisteret/api"


def search_companies(
    industry_code: str = "",
    min_employees: int = 5,
    max_employees: int = 50,
    municipality: str = "",
    name_query: str = "",
    page: int = 0,
    size: int = 20,
) -> list[dict]:
    """
    Søk etter norske AS i Brønnøysundregistrene.

    Args:
        industry_code:  NACE-kode, f.eks. "62" (IT) eller "41" (bygg)
        min_employees:  Minimum antall ansatte
        max_employees:  Maksimum antall ansatte
        municipality:   Kommunenavn, f.eks. "BODØ" eller "OSLO"
        name_query:     Fritekst i bedriftsnavn
        page:           Side (0-basert)
        size:           Resultater per side (maks 100)

    Returns:
        Liste med bedriftsdicts: {org_number, name, employees, industry, address, email, website}
    """
    params: dict = {
        "organisasjonsform": "AS",
        "size": min(size, 100),
        "page": page,
    }
    if industry_code:
        params["naeringskode"] = industry_code
    if municipality:
        params["kommunenavn"] = municipality.upper()
    if name_query:
        params["navn"] = name_query
    if min_employees:
        params["antallAnsatteStørreEnn"] = min_employees - 1
    if max_employees:
        params["antallAnsatteMindreEnn"] = max_employees + 1

    try:
        r = httpx.get(
            f"{BASE}/enheter",
            params=params,
            timeout=15,
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        data = r.json()
        enheter = data.get("_embedded", {}).get("enheter", [])
        logger.info(f"brreg: {len(enheter)} enheter funnet (side {page})")
        return [_normalize(e) for e in enheter]
    except httpx.HTTPStatusError as e:
        logger.error(f"brreg HTTP {e.response.status_code}: {e.response.text[:200]}")
        return []
    except Exception as e:
        logger.error(f"brreg søk feil: {e}")
        return []


def get_company(org_number: str) -> Optional[dict]:
    """
    Hent full info om én bedrift via org.nummer.

    Args:
        org_number: 9-sifret org.nummer (med eller uten mellomrom)

    Returns:
        Bedriftsdict eller None
    """
    org_number = org_number.replace(" ", "")
    try:
        r = httpx.get(
            f"{BASE}/enheter/{org_number}",
            timeout=10,
            headers={"Accept": "application/json"},
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return _normalize(r.json())
    except Exception as e:
        logger.error(f"brreg get_company {org_number} feil: {e}")
        return None


def find_leads(
    industry_code: str = "62",
    municipality: str = "",
    min_employees: int = 5,
    max_employees: int = 50,
    max_results: int = 30,
) -> list[dict]:
    """
    Shorthand: finn leads klar for outreach.

    Vanlige NACE-koder:
        62 — IT og programvare
        41 — Bygge- og anleggsvirksomhet
        47 — Detaljhandel
        56 — Restaurant og servering
        69 — Juridisk og regnskap
        70 — Ledelseskonsulentvirksomhet
        86 — Helsetjenester

    Returns:
        Leadliste med kun bedrifter som har registrert e-post
    """
    results = []
    page = 0
    while len(results) < max_results:
        batch = search_companies(
            industry_code=industry_code,
            municipality=municipality,
            min_employees=min_employees,
            max_employees=max_employees,
            page=page,
            size=min(50, max_results * 2),
        )
        if not batch:
            break
        # Prioriter de med e-post
        for company in batch:
            if len(results) >= max_results:
                break
            results.append(company)
        page += 1
        if len(batch) < 50:
            break
    return results[:max_results]


def _normalize(e: dict) -> dict:
    """Normaliser en enhet fra Brønnøysund til standard lead-format."""
    addr = e.get("forretningsadresse") or e.get("postadresse") or {}
    nace = e.get("naeringskode1") or {}
    return {
        "org_number": e.get("organisasjonsnummer", ""),
        "name": e.get("navn", ""),
        "employees": e.get("antallAnsatte", 0),
        "industry": nace.get("beskrivelse", ""),
        "industry_code": nace.get("kode", ""),
        "address": ", ".join(filter(None, [
            ", ".join(addr.get("adresse", [])),
            addr.get("postnummer", ""),
            addr.get("poststed", ""),
        ])),
        "municipality": addr.get("kommune", ""),
        "website": e.get("hjemmeside", ""),
        "email": e.get("epostadresse", ""),
        "org_form": e.get("organisasjonsform", {}).get("kode", ""),
        "registered": e.get("registreringsdatoEnhetsregisteret", ""),
        "bankrupt": e.get("konkurs", False),
        "source": "brreg",
    }
