"""
Lead finder and scorer. Combines Brønnøysund API, web search, and CRM to find
high-value leads for Nicholas's AI services.
"""
import logging
from dataclasses import dataclass, field

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)

BRREG_BASE = "https://data.brreg.no/enhetsregisteret/api"

# Norwegian municipality codes
MUNICIPALITY_CODES = {
    "Bodø": "1804",
    "Tromsø": "5401",
    "Narvik": "1806",
    "Mo i Rana": "1836",
    "Fauske": "1841",
}

# Industry codes most likely to benefit from AI agents
HIGH_VALUE_INDUSTRIES = {
    "56": "Restaurant og matservering",
    "96": "Frisør og skjønnhetspleie",
    "45": "Bilverksted og bilpleie",
    "68": "Eiendomsmegling",
    "86": "Helse og lege",
    "93": "Treningsstudio",
    "69": "Regnskap og revisjon",
    "55": "Hotell og overnatting",
    "61": "Telekommunikasjon",
    "62": "IT-konsulenter",
}


@dataclass
class Lead:
    org_number: str
    name: str
    city: str
    industry: str
    industry_name: str
    website: str = ""
    phone: str = ""
    email: str = ""
    score: int = 0
    pitch_angle: str = ""
    notes: list[str] = field(default_factory=list)


@with_retry()
def find_leads_brreg(municipality: str = "Bodø", industry_prefix: str | None = None, limit: int = 20) -> list[Lead]:
    """
    Find leads from the Norwegian Business Registry (Brønnøysund).

    Args:
        municipality: City name (mapped to municipality code)
        industry_prefix: NACE industry prefix (e.g. "56" for restaurants)
        limit: Max results

    Returns:
        List of Lead
    """
    code = MUNICIPALITY_CODES.get(municipality)
    if not code:
        raise ValueError(f"Unknown municipality: {municipality}. Available: {list(MUNICIPALITY_CODES.keys())}")

    params: dict = {
        "kommunenummer": code,
        "size": limit,
        "page": 0,
    }
    if industry_prefix:
        params["naeringskode"] = industry_prefix

    resp = httpx.get(
        f"{BRREG_BASE}/enheter",
        params=params,
        timeout=15.0,
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()

    data = resp.json()
    enheter = data.get("_embedded", {}).get("enheter", [])
    leads = []

    for e in enheter:
        industry_codes = e.get("naeringskode1", {}) or {}
        industry_code = str(industry_codes.get("kode", ""))[:2]
        industry_name = HIGH_VALUE_INDUSTRIES.get(industry_code, industry_codes.get("beskrivelse", ""))

        lead = Lead(
            org_number=e.get("organisasjonsnummer", ""),
            name=e.get("navn", ""),
            city=e.get("forretningsadresse", {}).get("poststed", municipality),
            industry=industry_code,
            industry_name=industry_name,
        )
        lead.score = _score_lead(lead, e)
        lead.pitch_angle = _pitch_angle(lead)
        leads.append(lead)

    leads.sort(key=lambda l: l.score, reverse=True)
    logger.info(f"Found {len(leads)} leads in {municipality}")
    return leads


def _score_lead(lead: Lead, raw_data: dict) -> int:
    """Score a lead 0-100 based on AI opportunity potential."""
    score = 50  # Base score

    # High-value industries get a boost
    if lead.industry in HIGH_VALUE_INDUSTRIES:
        score += 20

    # Has employees (bigger budget)
    if raw_data.get("antallAnsatte", 0) > 2:
        score += 10

    # Restaurant and service industries: highest priority
    if lead.industry in ("56", "96", "93", "68"):
        score += 15

    return min(score, 100)


def _pitch_angle(lead: Lead) -> str:
    """Generate a personalized pitch angle based on industry."""
    angles = {
        "56": "Mister du bookings mens du sover? Vi bygger AI-assistent som booker og svarer på spørsmål 24/7.",
        "96": "Vi kan redusere no-shows med 60% og automatisk rebooke kunder etter 6 uker.",
        "45": "Automatisk servicebooking utenom åpningstider og oppfølging etter service.",
        "68": "AI-boligvurdering og automatisk oppfølging av boligkjøper-leads.",
        "86": "Automatisk timebooking, påminnelser, og oppfølging etter konsultasjon.",
        "93": "Reduser frafall og øk oppmøte med AI-coaching og automatiske påminnelser.",
        "69": "AI-assistent som svarer på kundenes regnskapsspørsmål automatisk.",
        "55": "Automatisk gjestehåndtering, sjekkinn-instrukser, og oppsalg av rom.",
    }
    return angles.get(lead.industry, "Vi kan automatisere kundeservice og spare deg 5+ timer i uken.")


def format_leads_report(leads: list[Lead], limit: int = 5) -> str:
    """Format leads as a Telegram-friendly message."""
    lines = ["*Nye Leads*\n"]
    for lead in leads[:limit]:
        lines.append(
            f"*{lead.name}* (Score: {lead.score})\n"
            f"Bransje: {lead.industry_name}\n"
            f"Pitch: {lead.pitch_angle}\n"
            f"Org.nr: {lead.org_number}\n"
        )
    return "\n".join(lines)
