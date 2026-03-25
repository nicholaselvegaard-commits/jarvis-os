"""
NEXUS Selvlæring — leser og skriver egne erfaringer etter hver sesjon.

Etter hver kjøring lagrer NEXUS hva som fungerte og hva som ikke fungerte.
Disse lærdommene injiseres i neste sesjon — NEXUS bygger identitet over tid.

Lærdomsfil: /opt/nexus/memory/nexus_learnings.txt (max 50 linjer)
"""

import os
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

LEARNINGS_FILE = Path(__file__).parent / "nexus_learnings.txt"
MAX_LEARNINGS = 50


def load_learnings() -> str:
    """Les alle lagrede lærdomsverdier. Returnerer tom streng hvis ingen."""
    if not LEARNINGS_FILE.exists():
        return ""
    try:
        return LEARNINGS_FILE.read_text(encoding="utf-8").strip()
    except Exception as e:
        logger.warning(f"Kunne ikke lese learnings: {e}")
        return ""


def save_learning(insight: str, category: str = "general"):
    """
    Lagre én ny lærdom. Trimmer automatisk til MAX_LEARNINGS.

    Args:
        insight:  Hva NEXUS lærte (maks 120 tegn)
        category: "email" | "lead" | "strategy" | "general"
    """
    if not insight or len(insight.strip()) < 10:
        return

    timestamp = datetime.utcnow().strftime("%Y-%m-%d")
    line = f"[{timestamp}][{category}] {insight.strip()[:120]}"

    try:
        existing = []
        if LEARNINGS_FILE.exists():
            existing = LEARNINGS_FILE.read_text(encoding="utf-8").strip().splitlines()

        # Unngå duplikater
        if any(insight.strip()[:60] in e for e in existing):
            return

        existing.append(line)

        # Hold maks MAX_LEARNINGS linjer — fjern eldste
        if len(existing) > MAX_LEARNINGS:
            existing = existing[-MAX_LEARNINGS:]

        LEARNINGS_FILE.write_text("\n".join(existing) + "\n", encoding="utf-8")
        logger.info(f"Lærdom lagret: {line[:80]}")
    except Exception as e:
        logger.error(f"Kunne ikke lagre lærdom: {e}")


def save_session_learnings(state: dict):
    """
    Kalles etter hver kjøring for å ekstrahere og lagre lærdomsverdier.
    Brukes av orchestrator/reporter etter ferdig kjøring.
    """
    emails = state.get("emails_today", 0)
    leads = state.get("leads_contacted", 0)
    revenue = state.get("daily_revenue", 0)
    errors = state.get("errors", [])

    if emails >= 25:
        save_learning(f"E-post-mål nådd: {emails} sendt — fortsett samme strategi", "email")
    elif emails > 0:
        save_learning(f"Kun {emails} e-poster sendt — vurder å øke Apollo-volum", "strategy")

    if leads >= 10:
        save_learning(f"Lead-mål nådd: {leads} kontaktet — scoring-logikk fungerer", "lead")

    if revenue > 0:
        save_learning(f"Inntekt generert: {revenue} NOK — logg hvilken kanal som ga det", "strategy")

    for error in errors[-3:]:
        if "apollo" in error.lower():
            save_learning("Apollo API feiler — sjekk rate limits og nøkkel", "general")
        elif "instantly" in error.lower():
            save_learning("Instantly feiler — sjekk kampanje-status og domene-helse", "email")


def get_learnings_for_prompt() -> str:
    """Returner lærdomsverdier formatert for injeksjon i system-prompt."""
    content = load_learnings()
    if not content:
        return ""
    lines = content.strip().splitlines()
    recent = lines[-15:]  # Siste 15 lærdomsverdier
    return "\n\n[NEXUS LÆRDOMSVERDIER — hva som har fungert]:\n" + "\n".join(recent)
