"""
NEXUS Scheduler Service — Jordan's 9 jobs + NEXUS monitor/reflect jobs.

Jordan's jobs (Oslo timezone):
  03:00 — run_thinker (nightly research)
  03:30 — arxiv_nightly
  09:00 — trading_signal
  10:00 — autonomous_outreach
  12:00 — lead_scanner
  14:00 — website_scout
  16:00 — sub_agent_idle_work
  20:00 — autonomous_outreach (evening)
  21:00 — opportunity_scanner

NEXUS jobs:
  Every 30 min — monitor (email replies, goal milestones, system health)
  23:00         — reflection (daily self-improvement)
  Every 2h      — check_follow_ups (email follow-up scheduling)
"""
import logging
import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

if TYPE_CHECKING:
    from telegram.ext import Application

logger = logging.getLogger(__name__)

OSLO = pytz.timezone("Europe/Oslo")


# ── Jordan jobs ───────────────────────────────────────────────────────────────

def run_thinker():
    """Nightly research and knowledge update."""
    try:
        from agents.jordan.tools.research_agent import ResearchAgent
        agent = ResearchAgent()
        asyncio.run(agent.run("Scan for new revenue opportunities and tech trends. Update knowledge base."))
    except Exception as e:
        logger.warning(f"run_thinker feil: {e}")


def arxiv_nightly():
    """Scan arXiv for relevant AI papers."""
    try:
        from tools.arxiv import search_papers
        papers = search_papers(query="autonomous agents LLM", max_results=5)
        logger.info(f"arXiv nightly: {len(papers)} papers found")
    except Exception as e:
        logger.warning(f"arxiv_nightly feil: {e}")


def trading_signal():
    """Generate trading signals from market data."""
    try:
        from agents.jordan.tools.finance_agent import FinanceAgent
        agent = FinanceAgent()
        asyncio.run(agent.run("Generate morning market signals for BTC, ETH, and top Norwegian stocks."))
    except Exception as e:
        logger.warning(f"trading_signal feil: {e}")


def jarvis_autonomous_outreach():
    """Autonomous sales outreach — find and contact potential clients."""
    try:
        from agents.jordan.tools.sales_agent import SalesAgent
        agent = SalesAgent()
        asyncio.run(agent.run("Find 5 new potential clients for AI automation services in Norway. Draft outreach emails."))
    except Exception as e:
        logger.warning(f"autonomous_outreach feil: {e}")


def lead_scanner():
    """Scan for new leads using Apollo/Hunter."""
    try:
        from agents.jordan.tools.sales_agent import SalesAgent
        agent = SalesAgent()
        asyncio.run(agent.run("Scan Apollo for 10 new leads in Norway. Add to CRM."))
    except Exception as e:
        logger.warning(f"lead_scanner feil: {e}")


def website_scout():
    """Scout for businesses without websites or with outdated sites."""
    try:
        from agents.jordan.tools.scout_agent import ScoutAgent
        agent = ScoutAgent()
        asyncio.run(agent.run("Find 5 businesses in Bodø/Norway that need a new website. Log them."))
    except Exception as e:
        logger.warning(f"website_scout feil: {e}")


def sub_agent_idle_work():
    """Background autonomous work — whatever Jarvis thinks is most valuable."""
    try:
        from agents.jordan.tools.dev_agent import DevAgent
        agent = DevAgent()
        asyncio.run(agent.run("Check if any projects need updates or maintenance. Fix anything obvious."))
    except Exception as e:
        logger.warning(f"sub_agent_idle_work feil: {e}")


def opportunity_scanner():
    """Evening opportunity scan."""
    try:
        from agents.jordan.tools.scout_agent import ScoutAgent
        agent = ScoutAgent()
        asyncio.run(agent.run("Scan for arbitrage opportunities, new API launches, trending products. Score >7 only. Log findings."))
    except Exception as e:
        logger.warning(f"opportunity_scanner feil: {e}")


def content_pipeline():
    """Daily content generation for Nicholas's brand."""
    try:
        from agents.jordan.tools.content_agent import ContentAgent
        agent = ContentAgent()
        asyncio.run(agent.run("Generate today's content: tweet, LinkedIn post, Reddit comment about AI/tech trends relevant to a 17-year-old Norwegian founder."))
    except Exception as e:
        logger.warning(f"content_pipeline feil: {e}")


def finance_report():
    """Weekly financial intelligence report."""
    try:
        from agents.jordan.tools.finance_agent import FinanceAgent
        agent = FinanceAgent()
        asyncio.run(agent.run("Generate weekly financial report: crypto prices, Stripe revenue, Gumroad sales, burn rate, forecast."))
    except Exception as e:
        logger.warning(f"finance_report feil: {e}")


def self_improve():
    """Weekly self-improvement loop — read errors, auto-fix small bugs."""
    try:
        from agents.self_improve_agent import run_self_improve
        asyncio.run(run_self_improve())
    except Exception as e:
        logger.warning(f"self_improve feil: {e}")


def followup_outreach():
    """Follow up on leads that haven't responded in 3 days."""
    try:
        from agents.jordan.tools.sales_agent import SalesAgent
        from tools.crm import get_followup_due
        agent = SalesAgent()
        due = get_followup_due(days=3)
        if due:
            asyncio.run(agent.run(f"Send follow-up emails to these leads who haven't responded: {[l.get('name','?') for l in due[:5]]}"))
    except Exception as e:
        logger.warning(f"followup_outreach feil: {e}")


# ── NEXUS jobs ─────────────────────────────────────────────────────────────────

def nexus_monitor():
    """Check email replies, goal milestones, system health."""
    try:
        from agents.monitor_agent import run_sync
        count = run_sync()
        if count > 0:
            logger.info(f"Monitor: {count} varsler sendt")
    except Exception as e:
        logger.warning(f"nexus_monitor feil: {e}")


def nexus_reflect():
    """Daily self-reflection and strategy update."""
    try:
        from agents.reflection_agent import reflect_sync
        result = reflect_sync()
        logger.info(f"Refleksjon fullført: {result[:100]}")
    except Exception as e:
        logger.warning(f"nexus_reflect feil: {e}")


async def check_follow_ups_job(application):
    """Check for pending email follow-ups."""
    try:
        from interfaces.telegram_bot import check_follow_ups
        await check_follow_ups(application)
    except Exception as e:
        logger.warning(f"check_follow_ups feil: {e}")


def compress_memory_job():
    """Weekly compress old smart_memory entries — remove full_text, keep essence."""
    try:
        from memory.smart_memory import compress_old
        compress_old()
        logger.info("compress_memory_job: done")
    except Exception as e:
        logger.warning(f"compress_memory_job feil: {e}")


async def morning_summary_job(application):
    """07:00 daily summary — top ideas, overnight work, critical alerts."""
    import os
    chat_id = os.getenv("TELEGRAM_OWNER_CHAT_ID")
    if not chat_id:
        logger.warning("morning_summary: TELEGRAM_OWNER_CHAT_ID not set, skipping")
        return
    try:
        import anthropic
        from core.engine import _build_system_prompt
        from memory.smart_memory import get_context
        from memory.goals import format_for_telegram

        # Pull actual overnight context from memory
        overnight_context = get_context("hva skjedde natt morgen arbeid rapport", max_tokens=800)
        goal_status = format_for_telegram()

        prompt = (
            f"Lag en kort daglig oppdatering (07:00) til Nicholas basert på faktisk data:\n\n"
            f"=== MÅL-STATUS ===\n{goal_status}\n\n"
            f"=== HUKOMMELSE FRA I NATT ===\n{overnight_context or '(ingen registrert aktivitet)'}\n\n"
            "Basert på dette: gi en konkret 07:00-oppdatering:\n"
            "1. Hva skjedde i natt/morges? (kun det som faktisk ligger i hukommelsen)\n"
            "2. Topp 1-2 konkrete neste steg\n"
            "3. Kritiske varsler — kun hvis noe faktisk er kritisk\n\n"
            "KORTFATTET. Maks 150 ord. Gå rett på sak."
        )

        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=_build_system_prompt("jordan"),
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text if response.content else "Ingen oppdatering i dag."

        await application.bot.send_message(
            chat_id=int(chat_id), text=f"☀️ {text}", parse_mode="Markdown"
        )
        logger.info("morning_summary sendt")
    except Exception as e:
        logger.warning(f"morning_summary feil: {e}")


# ── Register all jobs ──────────────────────────────────────────────────────────

def register_jobs(scheduler: AsyncIOScheduler, application=None) -> None:
    """Register all Jordan + NEXUS scheduled jobs."""

    # ── Jordan jobs (Oslo timezone cron) ─────────────────────────────────────
    scheduler.add_job(
        run_thinker, trigger="cron", hour=3, minute=0,
        timezone=OSLO, id="run_thinker", replace_existing=True,
    )
    scheduler.add_job(
        arxiv_nightly, trigger="cron", hour=3, minute=30,
        timezone=OSLO, id="arxiv_nightly", replace_existing=True,
    )
    scheduler.add_job(
        trading_signal, trigger="cron", hour=9, minute=0,
        timezone=OSLO, id="trading_signal", replace_existing=True,
    )
    scheduler.add_job(
        jarvis_autonomous_outreach, trigger="cron", hour=10, minute=0,
        timezone=OSLO, id="outreach_morning", replace_existing=True,
    )
    scheduler.add_job(
        lead_scanner, trigger="cron", hour=12, minute=0,
        timezone=OSLO, id="lead_scanner", replace_existing=True,
    )
    scheduler.add_job(
        website_scout, trigger="cron", hour=14, minute=0,
        timezone=OSLO, id="website_scout", replace_existing=True,
    )
    scheduler.add_job(
        sub_agent_idle_work, trigger="cron", hour=16, minute=0,
        timezone=OSLO, id="sub_agent_idle", replace_existing=True,
    )
    scheduler.add_job(
        jarvis_autonomous_outreach, trigger="cron", hour=20, minute=0,
        timezone=OSLO, id="outreach_evening", replace_existing=True,
    )
    scheduler.add_job(
        opportunity_scanner, trigger="cron", hour=21, minute=0,
        timezone=OSLO, id="opportunity_scanner", replace_existing=True,
    )

    # ── NEXUS jobs ────────────────────────────────────────────────────────────
    scheduler.add_job(
        nexus_monitor, trigger="interval", minutes=30,
        id="nexus_monitor", replace_existing=True,
    )
    scheduler.add_job(
        nexus_reflect, trigger="cron", hour=23, minute=0,
        timezone=OSLO, id="nexus_reflect", replace_existing=True,
    )
    scheduler.add_job(
        compress_memory_job, trigger="cron", hour=4, minute=0, day_of_week="sun",
        timezone=OSLO, id="compress_memory", replace_existing=True,
    )
    scheduler.add_job(
        content_pipeline, trigger="cron", hour=8, minute=30,
        timezone=OSLO, id="content_pipeline", replace_existing=True,
    )
    scheduler.add_job(
        finance_report, trigger="cron", hour=12, minute=0, day_of_week="fri",
        timezone=OSLO, id="finance_report", replace_existing=True,
    )
    scheduler.add_job(
        self_improve, trigger="cron", hour=4, minute=30, day_of_week="mon",
        timezone=OSLO, id="self_improve", replace_existing=True,
    )
    scheduler.add_job(
        followup_outreach, trigger="cron", hour=11, minute=0,
        timezone=OSLO, id="followup_outreach", replace_existing=True,
    )

    # Jobs requiring the application object
    if application:
        scheduler.add_job(
            check_follow_ups_job, trigger="interval", hours=2,
            id="check_follow_ups", replace_existing=True,
            kwargs={"application": application},
        )
        scheduler.add_job(
            morning_summary_job, trigger="cron", hour=7, minute=0,
            timezone=OSLO, id="morning_summary", replace_existing=True,
            kwargs={"application": application},
        )

    logger.info(f"Scheduler: {len(scheduler.get_jobs())} jobs registrert")
