"""
NEXUS Monitor Agent — proaktive varsler uten at Nicholas trenger å spørre.

Sjekker kontinuerlig:
- E-postsvar fra leads
- Mål-fremgang (milepæler)
- Systemfeil og API-grenser
- Daglig aktivitetsoppsummering

Kalles fra scheduler (hvert 30. minutt) og autonomous_worker.
"""

import logging
import os
from datetime import datetime, date, timedelta
from pathlib import Path
import json

logger = logging.getLogger(__name__)

ALERT_STATE_FILE = Path(__file__).parent.parent / "memory" / "monitor_state.json"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
OWNER_CHAT_ID = os.getenv("TELEGRAM_OWNER_CHAT_ID", "")


def _load_state() -> dict:
    if ALERT_STATE_FILE.exists():
        try:
            return json.loads(ALERT_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    ALERT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ALERT_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _already_alerted(state: dict, key: str, cooldown_hours: int = 4) -> bool:
    """Sjekk om vi allerede har varslet om dette innenfor cooldown-perioden."""
    last = state.get(key)
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
        return (datetime.utcnow() - last_dt).total_seconds() < cooldown_hours * 3600
    except Exception:
        return False


def _mark_alerted(state: dict, key: str):
    state[key] = datetime.utcnow().isoformat()


async def _send_alert(message: str):
    """Send Telegram-varsel til Nicholas."""
    chat_id = OWNER_CHAT_ID
    if not chat_id or not TELEGRAM_TOKEN:
        logger.warning(f"MONITOR: {message}")
        return
    try:
        from telegram import Bot
        bot = Bot(token=TELEGRAM_TOKEN)
        async with bot:
            await bot.send_message(chat_id=int(chat_id), text=message)
        logger.info(f"Monitor-varsel sendt: {message[:80]}")
    except Exception as e:
        logger.error(f"Monitor send_alert feilet: {e}")


async def check_email_replies(state: dict) -> list:
    """Sjekk om noen leads har svart."""
    alerts = []
    try:
        from tools.email_reader import count_replies
        data = count_replies(days=1)
        if not data.get("configured"):
            return []

        replies = data.get("replies", 0)
        if replies > 0 and not _already_alerted(state, "email_replies", cooldown_hours=2):
            alerts.append(f"📧 {replies} lead(s) svarte på e-post! Sjekk innboksen og følg opp.")
            _mark_alerted(state, "email_replies")
    except Exception as e:
        logger.warning(f"check_email_replies feil: {e}")
    return alerts


async def check_goal_milestone(state: dict) -> list:
    """Sjekk om en ny milepæl er nådd."""
    alerts = []
    try:
        from memory.goals import get_status
        s = get_status()
        total = s["total_nok"]

        milestones = [1000, 5000, 10000, 25000, 50000, 75000, 100000]
        for ms in milestones:
            key = f"milestone_{ms}"
            if total >= ms and not _already_alerted(state, key, cooldown_hours=9999):
                alerts.append(f"🏆 MILEPÆL NÅdd! {ms:,} NOK totalt. {s['progress_pct']}% av målet.")
                _mark_alerted(state, key)
    except Exception as e:
        logger.warning(f"check_goal_milestone feil: {e}")
    return alerts


async def check_daily_summary(state: dict) -> list:
    """Send daglig oppsummering kl 20:00."""
    alerts = []
    hour = datetime.now().hour
    if hour != 20:
        return []
    if _already_alerted(state, "daily_summary", cooldown_hours=20):
        return []

    try:
        from memory.goals import get_status
        from memory.database import SessionLocal, ActivityLog
        s = get_status()

        with SessionLocal() as db:
            today_logs = db.query(ActivityLog).filter(
                ActivityLog.timestamp >= datetime.utcnow().replace(hour=0, minute=0, second=0)
            ).count()

        msg = (
            f"📊 DAGLIG OPPSUMMERING — {date.today().strftime('%d.%m.%Y')}\n\n"
            f"💰 Inntekt i dag: {s['today']['revenue']:,.0f} NOK\n"
            f"📧 E-poster sendt: {s['today']['emails_sent']}\n"
            f"👥 Leads kontaktet: {s['today']['leads_contacted']}\n"
            f"🎯 Totalt mot mål: {s['total_nok']:,.0f} / 100 000 NOK ({s['progress_pct']}%)\n"
            f"📝 Agenthandlinger: {today_logs}"
        )
        alerts.append(msg)
        _mark_alerted(state, "daily_summary")
    except Exception as e:
        logger.warning(f"check_daily_summary feil: {e}")
    return alerts


async def check_system_health(state: dict) -> list:
    """Sjekk systemhelse — Apollo, e-post, database."""
    alerts = []
    if _already_alerted(state, "system_health", cooldown_hours=6):
        return []

    issues = []
    try:
        from tools.apollo import ApolloClient
        ApolloClient()
    except Exception:
        issues.append("Apollo API ikke tilgjengelig")

    if issues and not _already_alerted(state, "system_issues", cooldown_hours=4):
        alerts.append(f"⚠️ Systemproblemer:\n" + "\n".join(f"• {i}" for i in issues))
        _mark_alerted(state, "system_issues")

    return alerts


async def run_all_checks() -> int:
    """
    Kjør alle monitorer. Returnerer antall varsler sendt.
    Kalles fra scheduler / autonomous_worker.
    """
    state = _load_state()
    all_alerts = []

    all_alerts += await check_email_replies(state)
    all_alerts += await check_goal_milestone(state)
    all_alerts += await check_daily_summary(state)
    all_alerts += await check_system_health(state)

    for alert in all_alerts:
        await _send_alert(alert)

    _save_state(state)
    return len(all_alerts)


def run_sync() -> int:
    """Synkron inngang for scheduler."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, run_all_checks()).result(timeout=60)
        else:
            return loop.run_until_complete(run_all_checks())
    except Exception as e:
        logger.error(f"monitor run_sync feil: {e}")
        return 0
