"""
Reporter Agent — Genererer daglig statusrapport med Reflexion og varsler eier.
"""

import os
import logging
from datetime import datetime
from core.state import NexusState
from tools.mcp_board import board
from tools.email_tool import notify_owner
from tools.ruflo_tool import store_campaign_stats, memory_search
from tools.platform_reporter import report_activity, update_kpi, report_run_complete, post_idea
from memory.self_learning import save_session_learnings
from anthropic import Anthropic

logger = logging.getLogger(__name__)
_anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))


def _run_reflexion(report: str, errors: list, emails: int, leads: int, revenue: float) -> str:
    """Selvkritikk: hva gikk bra, hva gikk dårlig, hva endres i morgen."""
    prompt = (
        f"Du er NEXUS. Her er dagens rapport:\n\n{report}\n\n"
        f"Gjør en kort post-mortem (maks 5 setninger):\n"
        f"1. Hva fungerte bra i dag?\n"
        f"2. Hva gikk dårlig eller kan forbedres?\n"
        f"3. Én konkret endring du gjør i morgen for bedre resultat.\n"
        f"Vær direkte og ærlig. Ikke pakk det inn."
    )
    try:
        resp = _anthropic.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.warning(f"Reflexion feilet: {e}")
        return "Reflexion utilgjengelig."


def reporter_node(state: NexusState) -> NexusState:
    """
    Genererer daglig rapport basert på dagens aktivitet, kjører Reflexion
    (selvkritikk + plan for i morgen), og sender til eier og Jordan.
    """
    now = datetime.utcnow()
    emails_today = state.get("emails_today", 0)
    emails_sent = state.get("emails_sent", [])
    mcp_inbox = state.get("mcp_inbox", [])
    mcp_sent = state.get("mcp_sent", [])
    errors = state.get("errors", [])

    daily_revenue    = state.get("daily_revenue", 0)
    leads_contacted  = state.get("leads_contacted", 0)
    meetings_booked  = state.get("meetings_booked", 0)
    api_costs        = state.get("api_costs_today", 0)

    # KPI-status
    kpi_revenue  = "✅" if daily_revenue >= 3300  else "❌"
    kpi_leads    = "✅" if leads_contacted >= 10   else "❌"
    kpi_emails   = "✅" if emails_today >= 25      else "❌"

    # Bygg rapporten
    report = f"""
=== NEXUS DAGLIG RAPPORT — {now.strftime('%Y-%m-%d %H:%M UTC')} ===

💰 INNTEKT I DAG:
  Fakturert:       {daily_revenue} NOK  {kpi_revenue} (mål: 3 300 NOK)
  Møter booket:    {meetings_booked}

📧 E-POST AKTIVITET:
  Sendt i dag:     {emails_today}  {kpi_emails} (mål: 25+)
  Kalde e-poster:  {sum(1 for e in emails_sent if e.get('action') == 'cold')}
  Oppfølginger:    {sum(1 for e in emails_sent if e.get('action') == 'followup')}

🎯 LEADS:
  Kontaktet i dag: {leads_contacted}  {kpi_leads} (mål: 10+)

📬 MCP-BOARD:
  Mottatte meldinger: {len(mcp_inbox)}
  Sendte svar:        {len(mcp_sent)}

💸 API-KOSTNADER:
  I dag:           {api_costs} NOK {"⚠️ OVER 500 NOK!" if api_costs > 500 else "OK"}

⚠️  FEIL:
  {len(errors)} feil registrert
{chr(10).join(f'  - {e}' for e in errors[-5:]) if errors else '  Ingen feil'}

📋 NESTE STEG:
  - Kjør research-scan kl 06:00 i morgen
  - Fortsett outreach kl 08:00
  - Godkjenn eventuelle avtaler over 500 NOK

— NEXUS
""".strip()

    # Lagre dagens stats i Ruflo for trend-analyse
    past_insights = memory_search("campaign stats revenue", limit=3)
    trend_text = ""
    if past_insights:
        trend_text = "\n\n📈 TREND (siste kjøringer):\n" + "\n".join(
            f"  - {e.get('value', e)}" for e in past_insights[:3]
        )
    store_campaign_stats(
        date=now.strftime("%Y-%m-%d"),
        emails_sent=emails_today,
        leads_scored=leads_contacted,
        revenue=daily_revenue,
        top_insight=f"{kpi_revenue} inntekt, {kpi_emails} e-poster",
    )

    # Reflexion — selvkritikk og konkret plan for i morgen
    reflexion = _run_reflexion(report, errors, emails_today, leads_contacted, daily_revenue)
    full_report = report + trend_text + f"\n\n🧠 REFLEXION:\n{reflexion}"

    # Selvlæring — lagre hva som fungerte denne kjøringen
    save_session_learnings(state)

    logger.info("Reporter: Sender daglig rapport med Reflexion")

    # ── Platform bridge — oppdater kontor-TV og feed ───────────────
    try:
        report_activity("nexus", f"📋 Daglig rapport klar: {emails_today} epost, {leads_contacted} leads, {daily_revenue} NOK", "desk")
        update_kpi(emails_sent=emails_today, leads_found=leads_contacted, revenue=int(daily_revenue), tasks_done=meetings_booked)
        report_run_complete("daglig", {"leads": leads_contacted, "emails_sent": emails_today, "revenue_est": int(daily_revenue), "tasks_done": meetings_booked})
        # Post reflexion as idea
        if reflexion and len(reflexion) > 20:
            post_idea("nexus", reflexion[:500], "reflexion")
    except Exception as _pe:
        logger.debug(f"Platform bridge: {_pe}")
    # ──────────────────────────────────────────────────────────────

    # Send til Jordan via MCP-board
    board.post_daily_report(full_report)

    # Send til eier via e-post
    notify_owner(
        subject=f"NEXUS Daglig Rapport — {now.strftime('%d.%m.%Y')}",
        body=full_report,
    )

    return {
        **state,
        "result": full_report,
        "next": "__end__",
        "daily_stats": {
            "date": now.isoformat(),
            "emails_sent": emails_today,
            "errors": len(errors),
            "mcp_messages": len(mcp_inbox),
            "daily_revenue": daily_revenue,
            "leads_contacted": leads_contacted,
            "meetings_booked": meetings_booked,
            "api_costs": api_costs,
        },
    }
