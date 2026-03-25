"""
Sales Agent — Sender kald e-post og oppfølginger til leads.
"""

import logging
import os
from datetime import datetime
from core.state import NexusState
from tools.email_tool import send_cold_email, send_followup_email
from memory.database import mark_lead_emailed, mark_lead_followed_up
from memory.self_learning import save_learning
from tools.platform_reporter import report_activity

logger = logging.getLogger(__name__)

MAX_EMAILS_PER_RUN = 25
INSTANTLY_CAMPAIGN_ID = os.getenv("INSTANTLY_CAMPAIGN_ID", "")


def sales_node(state: NexusState) -> NexusState:
    """
    Sender kald e-post til leads i køen.
    Skiller mellom ferske leads (kald e-post) og leads som trenger oppfølging.
    """
    leads = state.get("leads", [])
    emails_sent = state.get("emails_sent", [])
    emails_today = state.get("emails_today", 0)
    errors = state.get("errors", [])

    if not leads:
        logger.info("Sales Agent: Ingen leads i kø")
        report_activity("jordan", "Ingen leads i kø — venter", "desk")
        return {**state, "next": "mcp"}
    report_activity("jordan", f"Sender e-poster til {len(leads[:MAX_EMAILS_PER_RUN])} leads", "desk")

    sent_count = 0
    sent_log = []

    for lead in leads[:MAX_EMAILS_PER_RUN]:
        email = lead.get("email", "")
        if not email:
            continue

        is_followup = lead.get("needs_followup", False)
        days_since = lead.get("days_since_first_email", 3)
        action = "followup" if is_followup else "cold"
        success = False

        try:
            if is_followup:
                success = send_followup_email(lead, days_since=days_since)
                if success:
                    mark_lead_followed_up(lead["id"])
            else:
                success = send_cold_email(lead, campaign_id=INSTANTLY_CAMPAIGN_ID or None)
                if success:
                    mark_lead_emailed(lead["id"])

            if success:
                sent_count += 1
                sent_log.append({
                    "lead_id": lead.get("id"),
                    "to": email,
                    "company": lead.get("company", ""),
                    "action": action,
                    "sent_at": datetime.utcnow().isoformat(),
                })
                logger.info(f"Sales Agent: {action} e-post sendt til {email} ({lead.get('company', '')})")

        except Exception as e:
            err_msg = f"{datetime.utcnow().isoformat()} — Sales: Feil ved sending til {email}: {e}"
            logger.error(err_msg)
            errors.append(err_msg)

    logger.info(f"Sales Agent: Sendte {sent_count} e-poster denne runden")

    # Selvoptimering — logg strategi-observasjoner
    if sent_count == 0 and leads:
        save_learning("Ingen e-poster sendt til tross for leads — sjekk e-post-validering og Instantly-status", "email")
    elif sent_count >= 20:
        save_learning(f"Høyt e-postvolum ({sent_count}) — oppretthold samme kampanje-konfig", "email")

    # Logg hvilke bransjer som ble kontaktet
    companies_sent = [l.get("company", "") for l in leads[:sent_count] if l.get("company")]
    if companies_sent:
        save_learning(f"Kontaktet {sent_count} bedrifter inkl: {', '.join(companies_sent[:3])}", "lead")

    return {
        **state,
        "leads": [],
        "emails_sent": emails_sent + sent_log,
        "emails_today": emails_today + sent_count,
        "next": "mcp",
        "errors": errors,
    }
