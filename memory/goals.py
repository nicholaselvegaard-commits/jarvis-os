"""
NEXUS Goals — mål-tracking mot 100 000 NOK første måned.

Lagrer mål, milepæler og daglig fremgang i SQLite.
NEXUS kan oppdatere dette etter hver inntektsbegivenhet.
"""

import sqlite3
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "goals.db"
TARGET_NOK = 100_000

MILESTONES = [
    {"amount": 1_000,  "label": "Første krone",      "emoji": "🌱"},
    {"amount": 5_000,  "label": "5K — validert",     "emoji": "✅"},
    {"amount": 10_000, "label": "10K — momentum",    "emoji": "🚀"},
    {"amount": 25_000, "label": "25K — kvart vei",   "emoji": "💪"},
    {"amount": 50_000, "label": "50K — halvveis",    "emoji": "⚡"},
    {"amount": 75_000, "label": "75K — innspurt",    "emoji": "🔥"},
    {"amount": 100_000,"label": "100K — MÅLET NÅDD", "emoji": "🏆"},
]


def _get_db() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH), timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _init():
    with _get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS revenue_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                amount_nok REAL    NOT NULL,
                source     TEXT    NOT NULL,
                note       TEXT,
                created_at TEXT    DEFAULT (datetime('now'))
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS daily_goals (
                date       TEXT PRIMARY KEY,
                target_nok REAL DEFAULT 3334,
                actual_nok REAL DEFAULT 0,
                emails_sent INTEGER DEFAULT 0,
                leads_contacted INTEGER DEFAULT 0,
                note       TEXT
            )
        """)
        db.commit()


_init()


def add_revenue(amount_nok: float, source: str, note: str = "") -> Dict:
    """
    Registrer en inntektsbegivenhet.

    Args:
        amount_nok: Beløp i NOK
        source:     "consulting" | "saas" | "affiliate" | "other"
        note:       Valgfri beskrivelse
    """
    prev_total = get_total_revenue()  # capture BEFORE insert
    with _get_db() as db:
        db.execute(
            "INSERT INTO revenue_events (amount_nok, source, note) VALUES (?,?,?)",
            (amount_nok, source, note),
        )
        db.commit()

    total = get_total_revenue()
    milestone = _check_milestone(prev_total, total)
    logger.info(f"Inntekt registrert: {amount_nok} NOK fra {source}. Totalt: {total} NOK")
    return {"total": total, "new_milestone": milestone}


def get_total_revenue() -> float:
    """Hent total inntekt til nå."""
    with _get_db() as db:
        r = db.execute("SELECT COALESCE(SUM(amount_nok),0) FROM revenue_events").fetchone()
    return float(r[0])


def get_daily_revenue(target_date: Optional[str] = None) -> float:
    """Hent inntekt for én dag (default: i dag)."""
    d = target_date or date.today().isoformat()
    with _get_db() as db:
        r = db.execute(
            "SELECT COALESCE(SUM(amount_nok),0) FROM revenue_events WHERE date(created_at)=?",
            (d,),
        ).fetchone()
    return float(r[0])


def update_daily_stats(emails_sent: int = 0, leads_contacted: int = 0, revenue: float = 0.0):
    """Oppdater dagens statistikk (kalles fra scheduler/agents)."""
    today = date.today().isoformat()
    with _get_db() as db:
        db.execute("""
            INSERT INTO daily_goals (date, actual_nok, emails_sent, leads_contacted)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                actual_nok = actual_nok + excluded.actual_nok,
                emails_sent = emails_sent + excluded.emails_sent,
                leads_contacted = leads_contacted + excluded.leads_contacted
        """, (today, revenue, emails_sent, leads_contacted))
        db.commit()


def get_status() -> Dict:
    """Full status-rapport for mål og fremgang."""
    total = get_total_revenue()
    pct = round((total / TARGET_NOK) * 100, 1)
    remaining = max(0, TARGET_NOK - total)

    # Neste milepæl
    next_milestone = None
    for ms in MILESTONES:
        if total < ms["amount"]:
            next_milestone = ms
            break

    # Siste 7 dager daglig inntekt
    with _get_db() as db:
        recent = db.execute("""
            SELECT date(created_at) as day, SUM(amount_nok) as daily
            FROM revenue_events
            GROUP BY day
            ORDER BY day DESC
            LIMIT 7
        """).fetchall()

        today_stats = db.execute(
            "SELECT * FROM daily_goals WHERE date=?",
            (date.today().isoformat(),),
        ).fetchone()

    daily_avg = (sum(r["daily"] for r in recent) / len(recent)) if recent else 0
    days_to_goal = round(remaining / daily_avg) if daily_avg > 0 else None

    return {
        "total_nok": round(total, 2),
        "target_nok": TARGET_NOK,
        "progress_pct": pct,
        "remaining_nok": round(remaining, 2),
        "next_milestone": next_milestone,
        "daily_avg_nok": round(daily_avg, 2),
        "days_to_goal": days_to_goal,
        "today": {
            "revenue": get_daily_revenue(),
            "emails_sent": today_stats["emails_sent"] if today_stats else 0,
            "leads_contacted": today_stats["leads_contacted"] if today_stats else 0,
        },
    }


def format_for_telegram() -> str:
    """Formatert mål-status for Telegram."""
    s = get_status()
    bar_filled = int(s["progress_pct"] / 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)

    lines = [
        f"🎯 NEXUS — MÅL: 100 000 NOK",
        f"",
        f"[{bar}] {s['progress_pct']}%",
        f"Totalt: {s['total_nok']:,.0f} NOK",
        f"Gjenstår: {s['remaining_nok']:,.0f} NOK",
        f"",
    ]

    if s["next_milestone"]:
        ms = s["next_milestone"]
        lines.append(f"Neste: {ms['emoji']} {ms['label']} ({ms['amount']:,} NOK)")

    if s["daily_avg_nok"] > 0:
        lines.append(f"Snitt/dag: {s['daily_avg_nok']:,.0f} NOK")
    if s["days_to_goal"]:
        lines.append(f"Estimert ferdig: {s['days_to_goal']} dager")

    lines += [
        f"",
        f"I dag: {s['today']['revenue']:,.0f} NOK | "
        f"{s['today']['emails_sent']} e-poster | "
        f"{s['today']['leads_contacted']} leads",
    ]
    return "\n".join(lines)


def _check_milestone(prev_total: float, total: float) -> Optional[Dict]:
    """Sjekk om en ny milepæl er nådd. Returnerer milepæl-dict eller None."""
    for ms in MILESTONES:
        if prev_total < ms["amount"] <= total:
            return ms
    return None
