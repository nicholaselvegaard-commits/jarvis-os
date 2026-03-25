"""
Research Agent — Henter leads fra Apollo.io basert på aktive campaigns,
scorer dem, og beriker med nettside-info for personalisert outreach.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from core.state import NexusState
from tools.apollo import search_people, get_50_norwegian_leads
from tools.scraper import scrape_website, build_observation
from tools.ruflo_tool import store_lead_result, search_similar_leads
from memory.database import save_leads, get_leads_needing_followup
from tools.platform_reporter import report_activity, post_idea

logger = logging.getLogger(__name__)

CAMPAIGNS_FILE = Path(__file__).parent.parent / "campaigns.json"


def _load_active_campaigns() -> list:
    """Les aktive campaigns fra campaigns.json."""
    try:
        data = json.loads(CAMPAIGNS_FILE.read_text(encoding="utf-8"))
        active = [c for c in data.get("campaigns", []) if c.get("active")]
        logger.info(f"Research Agent: {len(active)} aktive campaigns lastet")
        return active
    except Exception as e:
        logger.warning(f"Kunne ikke lese campaigns.json: {e} — bruker standard")
        return []


def _score_lead(lead: dict) -> int:
    """
    Score et lead fra 1-10 basert på fit, urgency og datakvalitet.
    Kun leads med score 7+ sendes til outreach.
    """
    score = 5  # Baseline

    # Email verifisert = +2
    if lead.get("email"):
        score += 2

    # Har telefonnummer = +1
    if lead.get("phone"):
        score += 1

    # Riktig størrelse (10-100 ansatte = søt spot)
    size = lead.get("company_size", 0)
    try:
        size = int(size) if size else 0
        if 10 <= size <= 100:
            score += 1
        elif size > 100:
            score -= 1
    except (ValueError, TypeError):
        pass

    # Signaler fra nettside
    signals = lead.get("signals", [])
    if signals:
        score += min(len(signals), 2)

    # CEO/Founder = direkte beslutningstaker
    title = lead.get("title", "").lower()
    if any(t in title for t in ["ceo", "founder", "daglig leder", "eier", "administrerende"]):
        score += 1

    return min(score, 10)


def _enrich_lead_with_website(lead: dict) -> dict:
    """Skrap nettside og legg til observasjon + signaler."""
    website = lead.get("website", "")
    if not website:
        return lead

    scraped = scrape_website(website)
    if scraped:
        lead["signals"] = scraped.get("signals", [])
        lead["observation"] = build_observation(scraped)
        lead["website_description"] = scraped.get("description", "")
    return lead


def research_node(state: NexusState) -> NexusState:
    """
    1. Leser aktive campaigns
    2. Henter leads fra Apollo basert på campaign-config
    3. Skraper nettsider for personalisering
    4. Scorer alle leads (1-10) — kun 7+ går videre
    5. Henter leads som trenger oppfølging
    """
    logger.info("Research Agent: Starter")

    errors = state.get("errors", [])
    new_leads = []

    # Hent leads fra aktive campaigns
    campaigns = _load_active_campaigns()
    if campaigns:
        for campaign in campaigns:
            target = campaign.get("target", {})
            pitch = campaign.get("pitch", {})
            leads = search_people(
                job_titles=target.get("job_titles"),
                countries=target.get("countries", ["Norway"]),
                min_employees=target.get("min_employees", 5),
                max_employees=target.get("max_employees", 200),
                per_page=50,
            )
            # Berik hvert lead med campaign-info
            for lead in leads:
                lead["campaign_id"] = campaign.get("id")
                lead["pain_point"] = pitch.get("pain_point", "manuelle prosesser")
                lead["instantly_campaign_id"] = campaign.get("instantly_campaign_id", "")
            new_leads.extend(leads)
            logger.info(f"Campaign '{campaign['name']}': {len(leads)} leads")
    else:
        # Fallback: standard norske SMB-leads
        new_leads = get_50_norwegian_leads()

    logger.info(f"Research Agent: Totalt {len(new_leads)} råleads hentet")

    # Berik med nettside-info (maks 20 for å spare tid)
    enriched = []
    for lead in new_leads[:20]:
        enriched.append(_enrich_lead_with_website(lead))
    enriched.extend(new_leads[20:])  # Resten uten scraping
    new_leads = enriched

    # Score og filtrer
    for lead in new_leads:
        lead["score"] = _score_lead(lead)

    qualified = [l for l in new_leads if l.get("score", 0) >= 7]
    logger.info(f"Research Agent: {len(qualified)}/{len(new_leads)} leads kvalifisert (score 7+)")

    # Lagre til database
    if qualified:
        saved = save_leads(qualified)
        logger.info(f"Research Agent: Lagret {saved} leads til database")

    # Lagre lead-resultater i Ruflo vektorminne for fremtidig læring
    for lead in qualified[:10]:  # Maks 10 for å holde det raskt
        lead_id = lead.get("id") or lead.get("email", "unknown")
        company = lead.get("company", "Ukjent")
        score = lead.get("score", 0)
        observation = lead.get("observation", "Ingen observasjon")
        store_lead_result(lead_id, company, score, observation, "queued_for_outreach")

    # Hent leads som trenger oppfølging
    followup_leads = get_leads_needing_followup(days=3)
    logger.info(f"Research Agent: {len(followup_leads)} leads trenger oppfølging")

    all_leads = qualified + followup_leads

    if not all_leads:
        errors.append(f"{datetime.utcnow().isoformat()} — Research: Ingen kvalifiserte leads")

    return {
        **state,
        "leads": all_leads,
        "leads_contacted": len(qualified),
        "next": "sales" if all_leads else "__end__",
        "errors": errors,
    }
