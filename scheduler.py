"""
NEXUS Scheduler — Automatiske daglige rutiner.
  02:00 — AI Release Monitor: sjekk Anthropic, OpenAI, Google, Mistral for nye modeller
  06:00 — Research: lead-scanning + scoring
  08:00 — Morgenrutine: leads + e-poster + MCP
  12:00 — Middagsrutine: oppfølginger + innhold
  18:00 — Salgsrunde 2: voice + outreach
  20:00 — Daglig rapport til eier
  23:00 — Finanslogg: revenue-tracking + kostnader
"""

import logging
import sys
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


def ai_release_monitor():
    logger.info("=== AI RELEASE MONITOR (02:00) ===")
    from main import run
    run(
        task=(
            "AI Release Monitor: Sjekk Anthropic (anthropic.com/news), OpenAI (openai.com/news), "
            "Google DeepMind (deepmind.google/discover/blog), og Mistral (mistral.ai/news) for nye "
            "modeller eller API-endringer publisert de siste 24 timene. "
            "Hvis noe nytt er funnet: (1) lagre til memory med kategori 'models', "
            "(2) send Telegram-melding til Nicholas med hva som er nytt og hva det betyr for oss. "
            "Hvis ingenting nytt: logg 'Ingen nye AI-releases' og avslutt stille."
        ),
        task_type="research"
    )


def research_routine():
    logger.info("=== RESEARCH-RUTINE (06:00) ===")
    from main import run
    run(task="Research: Skann LinkedIn og Upwork for nye leads, score 1-10, forbered outreach for score 7+", task_type="research")


def morning_routine():
    logger.info("=== MORGENRUTINE (08:00) ===")
    from main import run
    run(task="Morgenrutine: Hent 50 leads fra Apollo.io, send personalisert outreach til score 7+ leads, sjekk MCP", task_type="morning_routine")


def midday_routine():
    logger.info("=== MIDDAGSRUTINE (12:00) ===")
    from main import run
    run(task="Middagsrutine: Oppfølginger til leads uten svar (3+ dager), publiser LinkedIn/Twitter innhold, svar MCP-board", task_type="sales")


def sales_round2():
    logger.info("=== SALGSRUNDE 2 (18:00) ===")
    from main import run
    run(task="Salgsrunde 2: Ring 10-20 bedrifter via Vapi.ai (uke 2+), send 10 nye outreach-meldinger", task_type="sales")


def daily_report():
    logger.info("=== DAGLIG RAPPORT (20:00) ===")
    from main import run
    run(task="Generer og send daglig rapport: inntekt i dag, leads kontaktet, møter booket, KPI-status vs mål", task_type="report")


def finance_log():
    logger.info("=== FINANSLOGG (23:00) ===")
    from main import run
    run(task="Finanslogg: oppdater revenue-tracker (fakturert/betalt/utestående), logg API-kostnader, alert hvis kostnad > 500 NOK", task_type="mcp")


def start_scheduler():
    scheduler = BlockingScheduler(timezone="Europe/Oslo")
    scheduler.add_job(ai_release_monitor, CronTrigger(hour=2,  minute=0), id="ai_monitor", misfire_grace_time=300)
    scheduler.add_job(research_routine,   CronTrigger(hour=6,  minute=0), id="research",   misfire_grace_time=300)
    scheduler.add_job(morning_routine,    CronTrigger(hour=8,  minute=0), id="morning",    misfire_grace_time=300)
    scheduler.add_job(midday_routine,     CronTrigger(hour=12, minute=0), id="midday",     misfire_grace_time=300)
    scheduler.add_job(sales_round2,       CronTrigger(hour=18, minute=0), id="sales2",     misfire_grace_time=300)
    scheduler.add_job(daily_report,       CronTrigger(hour=20, minute=0), id="report",     misfire_grace_time=300)
    scheduler.add_job(finance_log,        CronTrigger(hour=23, minute=0), id="finance",    misfire_grace_time=300)

    logger.info("NEXUS Scheduler aktiv — 02:00 / 06:00 / 08:00 / 12:00 / 18:00 / 20:00 / 23:00 (Europe/Oslo)")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stoppet")


if __name__ == "__main__":
    start_scheduler()
