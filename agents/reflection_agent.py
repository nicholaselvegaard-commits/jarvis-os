"""
NEXUS Reflection Agent — selvforbedring og strategijustering.

Analyserer egne resultater og oppdaterer strategi uten at Nicholas trenger å be om det.
Kjøres daglig (kl 23:00 via scheduler).

Hva den gjør:
1. Leser aktivitetslogg og inntektshistorikk
2. Kaller Claude for å analysere hva som fungerte / ikke fungerte
3. Lagrer innsikter i smart_memory
4. Oppdaterer NEXUS sin strategi-fil hvis nødvendig
"""

import logging
import os
from datetime import datetime, timedelta, date
from pathlib import Path

logger = logging.getLogger(__name__)

STRATEGY_FILE = Path(__file__).parent.parent / "memory" / "nexus_strategy.md"
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")


def _get_recent_activity(days: int = 7) -> str:
    """Hent aktivitetslogg siste N dager."""
    try:
        from memory.database import SessionLocal, ActivityLog
        cutoff = datetime.utcnow() - timedelta(days=days)
        with SessionLocal() as db:
            logs = db.query(ActivityLog).filter(
                ActivityLog.timestamp >= cutoff
            ).order_by(ActivityLog.timestamp.desc()).limit(100).all()

        if not logs:
            return "Ingen aktivitetslogg funnet."

        lines = []
        for log in logs:
            status = "✅" if log.success else "❌"
            lines.append(f"{status} [{log.agent}] {log.action}: {str(log.detail)[:100]}")
        return "\n".join(lines[:50])
    except Exception as e:
        return f"Kunne ikke laste aktivitetslogg: {e}"


def _get_performance_summary() -> str:
    """Hent ytelsessammendrag."""
    try:
        from memory.goals import get_status
        s = get_status()
        return (
            f"Totalt inntekt: {s['total_nok']:,.0f} NOK\n"
            f"Mål-fremgang: {s['progress_pct']}%\n"
            f"Daglig snitt: {s['daily_avg_nok']:,.0f} NOK\n"
            f"E-poster sendt i dag: {s['today']['emails_sent']}\n"
            f"Leads kontaktet i dag: {s['today']['leads_contacted']}"
        )
    except Exception as e:
        return f"Kunne ikke laste ytelsesdata: {e}"


def _load_current_strategy() -> str:
    """Les gjeldende strategi-fil."""
    if STRATEGY_FILE.exists():
        return STRATEGY_FILE.read_text(encoding="utf-8")[:3000]
    return "Ingen strategi definert ennå."


def _save_strategy(content: str):
    """Lagre oppdatert strategi."""
    STRATEGY_FILE.parent.mkdir(parents=True, exist_ok=True)
    STRATEGY_FILE.write_text(content, encoding="utf-8")


def _get_learnings() -> str:
    """Hent eksisterende lærdomsverdier."""
    try:
        from memory.self_learning import load_learnings
        return load_learnings()[-2000:]
    except Exception:
        return ""


async def reflect(force: bool = False) -> str:
    """
    Kjør selvrefleksjon. Returnerer innsikt-tekst.

    Args:
        force: Kjør selv om det ikke er på tide
    """
    if not ANTHROPIC_KEY:
        return "ANTHROPIC_API_KEY mangler — kan ikke reflektere."

    # Samle kontekst
    activity = _get_recent_activity(days=3)
    performance = _get_performance_summary()
    strategy = _load_current_strategy()
    learnings = _get_learnings()

    prompt = f"""Du er NEXUS — autonom AI-agent for Nicholas Elvegaard. Analyser din egen ytelse og forbedr strategien.

AKTIVITET SISTE 3 DAGER:
{activity}

YTELSE:
{performance}

GJELDENDE STRATEGI:
{strategy}

TIDLIGERE LÆRDOMSVERDIER:
{learnings or 'Ingen ennå.'}

Basert på dette:
1. Hva fungerte bra? (maks 3 punkter)
2. Hva fungerte dårlig? (maks 3 punkter)
3. Hva bør NEXUS gjøre annerledes neste uke? (maks 3 konkrete tiltak)
4. Oppdatert strategi (kort, handlingsrettet, maks 200 ord)

Svar på norsk. Vær konkret og direkte."""

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=ANTHROPIC_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        analysis = response.content[0].text

        # Lagre innsikter i smart_memory
        try:
            from memory.smart_memory import save
            save("learning", analysis[:500], ["refleksjon", "strategi", "analyse"], priority=3)
        except Exception:
            pass

        # Lagre i self_learning
        try:
            from memory.self_learning import save_learning
            lines = [l.strip() for l in analysis.splitlines() if len(l.strip()) > 20]
            for line in lines[:5]:
                save_learning(line[:120], "strategy")
        except Exception:
            pass

        # Oppdater strategi-fil
        today = date.today().strftime("%Y-%m-%d")
        new_strategy = f"# NEXUS Strategi — oppdatert {today}\n\n{analysis}\n"
        _save_strategy(new_strategy)

        logger.info("Refleksjon fullført og strategi oppdatert.")
        return analysis

    except Exception as e:
        logger.error(f"reflection_agent feil: {e}")
        return f"Refleksjon feilet: {e}"


def reflect_sync() -> str:
    """Synkron inngang for scheduler."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, reflect()).result(timeout=120)
        else:
            return loop.run_until_complete(reflect())
    except Exception as e:
        logger.error(f"reflect_sync feil: {e}")
        return f"Feil: {e}"


def get_current_strategy() -> str:
    """Hent gjeldende strategi for injeksjon i system-prompt."""
    content = _load_current_strategy()
    if content == "Ingen strategi definert ennå.":
        return ""
    return f"\n\n[NEXUS STRATEGI]:\n{content[:800]}"
