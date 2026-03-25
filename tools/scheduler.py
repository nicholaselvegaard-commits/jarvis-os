"""
Scheduled background tasks — Jarvis's autonomous world monitoring.

Schedule:
  03:00 — Thinker: fetch trends, cache opportunities (silent)
  03:30 — ArXiv: read new AI papers, update knowledge/tech.md (silent)
  Every 2h — Opportunity scanner: alert ONLY if something actionable found
  09:00 — Trading signal: alert ONLY on BUY/SELL (not HOLD)
  12:00 — Lead scanner: find and score new leads (silent cache)
"""
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from telegram.ext import Application

logger = logging.getLogger(__name__)


def _chat_id() -> str | None:
    ids = os.getenv("ALLOWED_CHAT_IDS", "").split(",")
    cid = ids[0].strip() if ids else ""
    return cid or None


async def _send(application: Application, text: str) -> None:
    chat_id = _chat_id()
    if not chat_id:
        return
    try:
        await application.bot.send_message(chat_id=int(chat_id), text=text, parse_mode="Markdown")
    except Exception as exc:
        logger.error(f"scheduler: failed to send message — {exc}")


def _cache_file(name: str) -> Path:
    cache_dir = Path("memory/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / name


# ─── 03:00 — Thinker (silent background) ──────────────────────────────────────

async def run_thinker(application: Application) -> None:
    """Fetch trends from multiple sources, cache opportunities for scanner. No notification."""
    logger.info("scheduler: thinker starting (silent)...")
    try:
        from tools.news_fetcher import fetch_all
        news = fetch_all(limit_per_source=5)
        seeds = [item.title for item in news[:15]]
        _cache_file("thinker_ideas.txt").write_text("\n".join(seeds), encoding="utf-8")
        logger.info(f"Thinker: cached {len(seeds)} idea seeds")
    except Exception as exc:
        logger.error(f"Thinker failed: {exc}", exc_info=True)


# ─── 03:30 — ArXiv learning (silent background) ───────────────────────────────

async def arxiv_nightly_update(application: Application) -> None:
    """Read new arxiv papers and append summaries to knowledge/tech.md. No notification."""
    logger.info("scheduler: arxiv nightly update (silent)...")
    try:
        from tools.arxiv import search, format_for_knowledge
        queries = [
            ("AI agents tool use", ["cs.AI"]),
            ("large language models inference", ["cs.LG"]),
            ("autonomous systems robotics", ["cs.RO"]),
        ]
        all_papers = []
        for query, cats in queries:
            papers = search(query, max_results=4, categories=cats)
            all_papers.extend(papers)
        if not all_papers:
            return
        knowledge_file = Path("knowledge/tech.md")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        section = f"\n\n---\n\n## ArXiv Updates — {today}\n\n" + format_for_knowledge(all_papers[:10])
        if knowledge_file.exists():
            import re
            current = knowledge_file.read_text(encoding="utf-8")
            current = re.sub(r"_Sist oppdatert: [\d-]+_", f"_Sist oppdatert: {today}_", current)
            knowledge_file.write_text(current + section, encoding="utf-8")
        logger.info(f"ArXiv: appended {len(all_papers)} papers to knowledge/tech.md")
    except Exception as exc:
        logger.error(f"ArXiv update failed: {exc}", exc_info=True)


# ─── Every 2h — Opportunity scanner (alerts only when actionable) ──────────────

async def opportunity_scanner(application: Application) -> None:
    """
    Scans world events, markets and trends.
    Sends Telegram alert ONLY if a real money opportunity is found.
    Threshold: market move >3%, major news that changes a sector, new business opening.
    """
    logger.info("scheduler: scanning for opportunities...")
    opportunities = []

    # 1. Check for big market moves
    try:
        from tools.market_data import get_quote
        watchlist = {
            "BTC-USD": "Bitcoin",
            "ETH-USD": "Ethereum",
            "EQNR.OL": "Equinor",
            "NVDA": "Nvidia",
            "MSFT": "Microsoft",
            "^OSEAX": "Oslo Børs",
        }
        for ticker, name in watchlist.items():
            try:
                q = get_quote(ticker)
                change = q.get("change_pct", 0)
                price = q.get("price", 0)
                if abs(change) >= 3.0:
                    direction = "🚀" if change > 0 else "💥"
                    opportunities.append(
                        f"{direction} *{name}* ({ticker}): {change:+.1f}% — ${price:,.2f}\n"
                        f"  → Stor bevegelse. Hva driver dette?"
                    )
            except Exception:
                pass
    except Exception as exc:
        logger.warning(f"Opportunity scanner: market check failed — {exc}")

    # 2. Check news for major events (company launches, regulation, tech breakthroughs)
    try:
        from tools.news_fetcher import fetch_all
        news = fetch_all(limit_per_source=3)
        money_keywords = [
            "billion", "milliard", "acquisition", "IPO", "bankrupt", "ban", "regulation",
            "breakthrough", "raises", "funding", "AI", "crypto", "collapse", "surge",
            "gjennombrudd", "oppkjøp", "konkurs", "forbud", "millioner"
        ]
        for item in news[:20]:
            title_lower = item.title.lower()
            hits = sum(1 for kw in money_keywords if kw.lower() in title_lower)
            if hits >= 2:
                opportunities.append(
                    f"📰 *{item.title}*\n"
                    f"  → {item.source if hasattr(item, 'source') else 'Nyhet'} — kan dette gi en mulighet?"
                )
                if len([o for o in opportunities if o.startswith("📰")]) >= 2:
                    break
    except Exception as exc:
        logger.warning(f"Opportunity scanner: news check failed — {exc}")

    # Only send if there's something worth acting on
    if opportunities:
        msg = "⚡ *Jarvis har funnet en mulighet*\n\n"
        msg += "\n\n".join(opportunities[:4])
        msg += "\n\n_Svar for å analysere videre eller handle nå._"
        await _send(application, msg)
        logger.info(f"Opportunity scanner: sent alert with {len(opportunities)} opportunities")
    else:
        logger.info("Opportunity scanner: nothing actionable found, staying silent")


# ─── 09:00 — Trading signal (BUY/SELL only — no HOLD spam) ───────────────────

async def trading_signal(application: Application) -> None:
    """Send trading signal ONLY on BUY or SELL — never sends HOLD."""
    logger.info("scheduler: trading signal check...")
    try:
        from tools.market_data import get_history, get_quote
        signals = []
        for ticker in ["BTC-USD", "ETH-USD", "EQNR.OL", "NVDA"]:
            try:
                hist = get_history(ticker, period="3mo", interval="1d")
                if len(hist) < 20:
                    continue
                closes = [h["close"] for h in hist]
                sma20 = sum(closes[-20:]) / 20
                sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else sma20
                current = closes[-1]
                prev = closes[-2]
                change = (current - prev) / prev * 100

                if current > sma20 > sma50:
                    signal = "BUY 🟢"
                elif current < sma20 < sma50:
                    signal = "SELL 🔴"
                else:
                    continue  # HOLD — no message

                signals.append(f"*{ticker}*: {signal} — ${current:,.2f} ({change:+.1f}%)")
            except Exception:
                pass

        if signals:
            msg = "📈 *Trading Signal*\n\n" + "\n".join(signals)
            msg += "\n\n_SMA20/SMA50 crossover. Ikke finansiell rådgivning._"
            await _send(application, msg)
    except Exception as exc:
        logger.error(f"Trading signal failed: {exc}", exc_info=True)


# ─── 12:00 — Lead scanner (silent cache, Jarvis uses on demand) ───────────────

async def lead_scanner(application: Application) -> None:
    """Silently fetch and cache fresh leads. Jarvis delivers them when Nicholas asks."""
    logger.info("scheduler: scanning for leads (silent)...")
    try:
        from tools.lead_agent import find_leads_brreg
        leads = find_leads_brreg(municipality="Bodø", limit=10)
        if leads:
            lines = [f"{l.name} | {l.industry} | {l.pitch_angle[:80]}" for l in leads]
            _cache_file("fresh_leads.txt").write_text("\n".join(lines), encoding="utf-8")
            logger.info(f"Lead scanner: cached {len(leads)} leads")
    except Exception as exc:
        logger.warning(f"Lead scanner failed: {exc}", exc_info=True)


# ─── 10:00 & 20:00 — Jarvis autonomous outreach (silent, works without Nicholas) ─

async def jarvis_autonomous_outreach(application: Application) -> None:
    """
    Jarvis works on his own — reads cached leads, crafts and sends pitch emails
    from his own address (jordan.develepor@outlook.com). No approval needed.
    Only contacts Nicholas if he finds something requiring >200kr or a big decision.
    """
    logger.info("scheduler: Jarvis autonomous outreach starting...")
    try:
        import agent

        # Load cached leads (from lead_scanner at 12:00)
        leads_cache = _cache_file("fresh_leads.txt")
        lead_context = ""
        if leads_cache.exists():
            lead_context = leads_cache.read_text(encoding="utf-8")[:2000]

        # Load thinker ideas (from 03:00)
        thinker_cache = _cache_file("thinker_ideas.txt")
        idea_context = ""
        if thinker_cache.exists():
            idea_context = thinker_cache.read_text(encoding="utf-8")[:1000]

        prompt = f"""[AUTONOMOUS WORK SESSION]

Du jobber nå uten at Nicholas er til stede. Bruk din egen email (jarvis_email tool) til å:
1. Velg 1-2 bedrifter fra lead-cachen under som ser lovende ut
2. Analyser hva AI kan gjøre for dem (15 sek research)
3. Skriv og SEND en konkret pitch-epost fra din egen adresse — ikke foreslå, bare gjør det
4. Logg til CRM med resultatet

Husk: Din email = din identitet. Nicholas trenger ikke godkjenne dette.
Etter jobbing: skriv en kort notat til jarvis_notebook om hva du gjorde.

Lead-cache:
{lead_context if lead_context else "Ingen leads cached ennå — gjør en rask søk på Brreg i stedet."}

Trends/ideer fra thinker:
{idea_context if idea_context else "Ingen ideer cached."}

Stopp og send Telegram BARE hvis noe krever >200kr eller en stor beslutning fra Nicholas.
"""
        # Fire the agent with a background-style send function
        chat_id = _chat_id()

        async def background_send(to_chat_id: str, text: str, reply_markup: dict | None = None) -> None:
            # Only forward ESCALATION messages (Jarvis flagged as needing Nicholas)
            if any(kw in text.lower() for kw in ["trenger godkjenning", "hva synes du", "skal jeg", "bør jeg", "200kr"]):
                await _send(application, text)

        response = await agent.run(
            user_message=prompt,
            chat_id=f"autonomous_{chat_id}",
            telegram_send=background_send,
        )
        if response:
            logger.info(f"Jarvis autonomous outreach done: {response[:200]}")

    except Exception as exc:
        logger.error(f"Jarvis autonomous outreach failed: {exc}", exc_info=True)


# ─── 14:00 — Website scout (find businesses without websites, build demos) ────

async def website_scout_job(application: Application) -> None:
    """
    Jarvis finds businesses without websites, builds demo sites, notifies Nicholas.
    Runs silently — only sends Telegram when a demo is ready.
    """
    logger.info("scheduler: website scout starting...")
    try:
        from tools.website_scout import scout_and_build

        async def notify(text: str) -> None:
            await _send(application, text)

        results = await scout_and_build(
            location="Bodø",
            max_targets=2,
            notify_fn=notify,
        )
        if results:
            logger.info(f"Website scout: built {len(results)} demos")
        else:
            logger.info("Website scout: no new targets found this run")
    except Exception as exc:
        logger.error(f"Website scout failed: {exc}", exc_info=True)


# ─── Sub-agent idle work (runs when no Jarvis task is queued) ─────────────────

async def sub_agent_idle_work(application: Application) -> None:
    """
    When sub-agents have nothing to do, they run self-assigned tasks:
    - research: scan latest AI tools and write to knowledge/tech.md
    - scout: check for new free APIs
    - finance: quick market update
    Runs silently, logs to Supabase.
    """
    logger.info("scheduler: sub-agent idle work starting...")
    try:
        from tools.delegate import delegate

        idle_tasks = [
            ("research", "Scan for the top 3 AI tools released this week. Write a 200-word summary."),
            ("scout", "Find 3 new free APIs released this week that could be useful for an AI business agent."),
            ("finance", "Give a quick market pulse: BTC, ETH, NVDA — up or down this week and why?"),
        ]

        # Pick one at random to avoid always running the same one
        import random
        agent_name, task = random.choice(idle_tasks)

        logger.info(f"scheduler: idle work → {agent_name}: {task[:60]}")
        result = await delegate(agent=agent_name, task=task)
        logger.info(f"scheduler: idle {agent_name} done: {result[:100]}")

    except Exception as exc:
        logger.error(f"Sub-agent idle work failed: {exc}", exc_info=True)


# ─── Legacy aliases ───────────────────────────────────────────────────────────

async def morning_report(application: Application) -> None:
    """Legacy alias — replaced by opportunity_scanner."""
    await opportunity_scanner(application)

async def morning_email_check(application: Application) -> None:
    """Legacy alias."""
    await opportunity_scanner(application)

async def midday_update(application: Application) -> None:
    """Legacy alias — replaced by lead_scanner."""
    await lead_scanner(application)

async def evening_report(application: Application) -> None:
    """Legacy alias — replaced by opportunity_scanner."""
    await opportunity_scanner(application)


# ─── Registration ─────────────────────────────────────────────────────────────

def register_jobs(scheduler, application: Application) -> None:
    """Register all scheduled tasks with APScheduler."""
    tz = "Europe/Oslo"

    jobs = [
        (run_thinker,                 "cron", dict(hour=3,  minute=0),  "thinker"),
        (arxiv_nightly_update,        "cron", dict(hour=3,  minute=30), "arxiv_update"),
        (trading_signal,              "cron", dict(hour=9,  minute=0),  "trading_signal"),
        (jarvis_autonomous_outreach,  "cron", dict(hour=10, minute=0),  "jarvis_outreach_am"),
        (lead_scanner,                "cron", dict(hour=12, minute=0),  "midday_update"),
        (website_scout_job,           "cron", dict(hour=14, minute=0),  "website_scout"),
        (sub_agent_idle_work,         "cron", dict(hour=16, minute=0),  "idle_work"),
        (jarvis_autonomous_outreach,  "cron", dict(hour=20, minute=0),  "jarvis_outreach_pm"),
        (opportunity_scanner,         "cron", dict(hour=21, minute=0),  "evening_report"),
    ]

    for func, trigger, kwargs, job_id in jobs:
        scheduler.add_job(
            func,
            trigger=trigger,
            timezone=tz if trigger == "cron" else None,
            args=[application],
            id=job_id,
            replace_existing=True,
            **kwargs,
        )
        if trigger == "cron":
            logger.info(f"Scheduled: {job_id} at {kwargs.get('hour','?')}:{str(kwargs.get('minute','0')).zfill(2)} {tz}")
        else:
            logger.info(f"Scheduled: {job_id} every {kwargs.get('hours','?')}h")
