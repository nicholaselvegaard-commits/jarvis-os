"""
NEXUS Scheduler — Automatiske daglige rutiner.

  06:00 — Lead pipeline: Brreg-scan, scoring, KG-lagring
  08:00 — Morgenrutine: worker-orkestrasjon + e-poster + MCP
  12:00 — Middagsrutine: oppfølginger + lead pipeline runde 2
  18:00 — Salgsrunde 2: outreach + innhold
  20:00 — Daglig rapport til eier
  23:00 — Finanslogg + selvrefleksjon
"""

import logging
import sys
import os
from pathlib import Path
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv()
Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/scheduler.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("nexus.scheduler")

# Sørg for at /opt/nexus er i path
_NEXUS = Path("/opt/nexus")
if str(_NEXUS) not in sys.path:
    sys.path.insert(0, str(_NEXUS))


def _notify(message: str):
    """Send kort varsling til Nicholas via Telegram."""
    try:
        from tools.telegram_bot import notify_owner
        notify_owner(message)
    except Exception as e:
        logger.warning(f"Telegram varsling feilet: {e}")


# ── 06:00 — Lead Pipeline ─────────────────────────────────────────────────────

def lead_pipeline_routine():
    logger.info("=== LEAD PIPELINE (06:00) ===")
    try:
        from workers.lead_pipeline import run_lead_pipeline, format_report
        stats = run_lead_pipeline(
            cities=["Bodø", "Oslo", "Tromsø", "Trondheim", "Bergen"],
            min_score=6,
            max_leads_per_run=40,
        )
        report = format_report(stats)
        logger.info(f"Lead pipeline ferdig: {stats.get('qualified', 0)} kvalifiserte leads")
        _notify(f"[06:00] {report}")
    except Exception as e:
        logger.error(f"Lead pipeline feil: {e}", exc_info=True)
        _notify(f"[06:00] Lead pipeline feil: {e}")


# ── 08:00 — Morgenrutine ──────────────────────────────────────────────────────

def morning_routine():
    logger.info("=== MORGENRUTINE (08:00) ===")

    # 1. Orkestrér morgenoppgaver via workers
    try:
        from workers.orchestrator import Orchestrator
        orch = Orchestrator()
        result = orch.delegate(
            "Morgenrutine: "
            "1) Sjekk om det er lead-svar i e-posten (siste 12 timer), "
            "2) Hent og score 10 leads fra Brreg for IT-bedrifter i Bodø og Tromsø, "
            "3) Send e-poster til de beste 5 nye leadene, "
            "4) Oppdater daglig notat i Obsidian med status."
        )
        summary = result.get("summary", "")
        ms = result.get("duration_ms", 0)
        workers = ", ".join(result.get("workers_used", []))
        logger.info(f"Morgenrutine delegert: {workers} — {ms}ms")
        _notify(f"[08:00] Morgenrutine\nArbeidere: {workers}\n\n{summary[:500]}")
    except Exception as e:
        logger.error(f"Morgenrutine worker-feil: {e}", exc_info=True)
        # Fallback til gammel LangGraph
        try:
            from main import run
            run(
                task="Morgenrutine: Hent 50 leads fra Apollo.io, send personalisert outreach til score 7+ leads, sjekk MCP",
                task_type="morning_routine",
            )
        except Exception as e2:
            logger.error(f"Morgenrutine fallback feil: {e2}")
            _notify(f"[08:00] Morgenrutine feil: {e}")


# ── 12:00 — Middagsrutine ─────────────────────────────────────────────────────

def midday_routine():
    logger.info("=== MIDDAGSRUTINE (12:00) ===")

    # Lead pipeline runde 2 (andre byer)
    try:
        from workers.lead_pipeline import run_lead_pipeline, format_report
        stats = run_lead_pipeline(
            cities=["Stavanger", "Kristiansand", "Drammen"],
            min_score=6,
            max_leads_per_run=20,
        )
        report = format_report(stats)
        logger.info(f"Middag pipeline: {stats.get('qualified', 0)} leads")
    except Exception as e:
        logger.error(f"Middag pipeline feil: {e}")
        report = f"Pipeline feil: {e}"

    # Oppfølgingsarbeid via workers
    try:
        from workers.orchestrator import Orchestrator
        orch = Orchestrator()
        result = orch.run_parallel([
            ("memory", "Sjekk og oppdater KG med leads fra morgens outreach. Legg til edge 'contacted' mellom nicholas og nye leads."),
            ("analytics", "Hent oppdatert revenue-status fra Stripe. Beregn fremgang mot 100 000 NOK."),
        ])
        for r in result:
            if not r.get("success"):
                logger.warning(f"Middag worker feil [{r.get('worker')}]: {r.get('result', '')[:100]}")
    except Exception as e:
        logger.error(f"Middag workers feil: {e}")

    _notify(f"[12:00] Middagsrutine\n{report[:400]}")


# ── 18:00 — Salgsrunde 2 ─────────────────────────────────────────────────────

def sales_round2():
    logger.info("=== SALGSRUNDE 2 (18:00) ===")
    try:
        from workers.orchestrator import Orchestrator
        orch = Orchestrator()
        result = orch.delegate(
            "Salgsrunde 2: "
            "1) Finn 10 leads i KG som ble lagt til i dag men ikke kontaktet, "
            "2) Skriv personaliserte LinkedIn-meldinger til topp 5 leads, "
            "3) Publiser ett LinkedIn-innlegg om AI-automatisering for norske SMB-bedrifter, "
            "4) Sjekk om det er svar på morgendagens e-poster."
        )
        summary = result.get("summary", "")
        ms = result.get("duration_ms", 0)
        _notify(f"[18:00] Salgsrunde 2 ({ms}ms)\n{summary[:500]}")
    except Exception as e:
        logger.error(f"Salgsrunde 2 feil: {e}", exc_info=True)
        try:
            from main import run
            run(task="Salgsrunde 2: Ring 10-20 bedrifter via Vapi.ai (uke 2+), send 10 nye outreach-meldinger", task_type="sales")
        except Exception as e2:
            logger.error(f"Salgsrunde 2 fallback feil: {e2}")
            _notify(f"[18:00] Salgsrunde 2 feil: {e}")


# ── 20:00 — Daglig rapport ────────────────────────────────────────────────────

def daily_report():
    logger.info("=== DAGLIG RAPPORT (20:00) ===")
    try:
        from workers.orchestrator import Orchestrator
        orch = Orchestrator()

        # Hent metrics parallelt
        results = orch.run_parallel([
            ("analytics", "Hent dagens totale revenue fra Stripe og Gumroad. Vis i NOK."),
            ("memory", "Tell opp: hvor mange nye leads ble lagt til i KG i dag? Hvor mange fikk score>=6?"),
        ])

        # Bygg rapport
        from main import run as legacy_run
        state = legacy_run(task="Generer og send daglig rapport: inntekt i dag, leads kontaktet, møter booket, KPI-status vs mål", task_type="report")
        report_text = state.get("result", "Rapport ikke tilgjengelig")

        # Lagre rapport i Obsidian
        try:
            if str(_NEXUS) not in sys.path:
                sys.path.insert(0, str(_NEXUS))
            from memory.brain import Brain
            b = Brain()
            if b.obsidian:
                b.obsidian.daily_note(f"\n## Daglig rapport {__import__('datetime').datetime.now().strftime('%H:%M')}\n{report_text[:1000]}")
        except Exception:
            pass

        _notify(f"[20:00] {report_text[:2000]}")
    except Exception as e:
        logger.error(f"Daglig rapport feil: {e}", exc_info=True)
        _notify(f"[20:00] Rapport feil: {e}")


# ── 23:00 — Finanslogg + selvrefleksjon ──────────────────────────────────────

def self_improve_routine():
    logger.info("=== SELVFORBEDRING (23:30) ===")
    try:
        from agents.self_improve.self_improve import run_self_improvement
        result = run_self_improvement()
        score = result.get("score", "?")
        summary = result.get("summary", "")
        lessons = len(result.get("lessons", []))
        _notify(f"[23:30] Selvforbedring score={score}/10\n{summary}\n{lessons} nye lærdommer lagret.")
    except Exception as e:
        logger.error(f"Selvforbedring feil: {e}")


def finance_and_reflect():
    logger.info("=== FINANSLOGG + REFLEKSJON (23:00) ===")

    # Finanslogg via workers
    try:
        from workers.orchestrator import Orchestrator
        orch = Orchestrator()
        result = orch.run_parallel([
            ("analytics", "Finanslogg: hent alle Stripe-transaksjoner i dag. Beregn fakturert/betalt/utestående. Alert hvis API-kostnad > 500 NOK."),
            ("memory", "Oppdater KG med dagens aktivitet: antall kontaktede leads, svar mottatt, deals i pipeline."),
        ])
        for r in result:
            logger.info(f"  [{r.get('worker')}] {r.get('result','')[:100]}")
    except Exception as e:
        logger.error(f"Finanslogg workers feil: {e}")

    # Selvrefleksjon
    try:
        import asyncio
        from agents.reflection_agent import reflect
        reflection = asyncio.run(reflect(force=True))
        logger.info(f"Refleksjon: {str(reflection)[:200]}")

        # Lagre refleksjon i brain
        try:
            if str(_NEXUS) not in sys.path:
                sys.path.insert(0, str(_NEXUS))
            from memory.brain import Brain
            b = Brain()
            b.remember(
                str(reflection)[:500],
                category="learning",
                tags=["refleksjon", "daglig"],
            )
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Selvrefleksjon feil: {e}")

    _notify(f"[23:00] Finanslogg og refleksjon fullfort. God natt.")


# ── Start scheduler ───────────────────────────────────────────────────────────

def start_scheduler():
    scheduler = BlockingScheduler(timezone="Europe/Oslo")

    scheduler.add_job(lead_pipeline_routine, CronTrigger(hour=6,  minute=0),  id="lead_pipeline",  misfire_grace_time=300)
    scheduler.add_job(morning_routine,       CronTrigger(hour=8,  minute=0),  id="morning",        misfire_grace_time=300)
    scheduler.add_job(midday_routine,        CronTrigger(hour=12, minute=0),  id="midday",         misfire_grace_time=300)
    scheduler.add_job(sales_round2,          CronTrigger(hour=18, minute=0),  id="sales2",         misfire_grace_time=300)
    scheduler.add_job(daily_report,          CronTrigger(hour=20, minute=0),  id="report",         misfire_grace_time=300)
    scheduler.add_job(finance_and_reflect,   CronTrigger(hour=23, minute=0),  id="finance",        misfire_grace_time=300)
    scheduler.add_job(self_improve_routine,  CronTrigger(hour=23, minute=30), id="self_improve",   misfire_grace_time=300)

    logger.info(
        "NEXUS Scheduler aktiv — "
        "06:00 lead pipeline | 08:00 morgen | 12:00 middag | "
        "18:00 salg | 20:00 rapport | 23:00 finans+refleksjon (Europe/Oslo)"
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stoppet")


if __name__ == "__main__":
    start_scheduler()
