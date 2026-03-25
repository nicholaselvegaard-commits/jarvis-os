"""
NEXUS Database — Persistent minne for leads, e-poster og aktivitetslogg.

Bruker SQLite (enkelt å starte, lett å migrere til PostgreSQL).
"""

import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy import (
    create_engine, Column, String, Integer, Boolean,
    DateTime, Text, Float, event
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///nexus.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()


# ---------------------------------------------------------------------------
# Modeller
# ---------------------------------------------------------------------------

class Lead(Base):
    __tablename__ = "leads"

    id = Column(String, primary_key=True)
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String, unique=True, index=True)
    title = Column(String)
    company = Column(String)
    company_size = Column(String)
    industry = Column(String)
    phone = Column(String)
    linkedin_url = Column(String)
    city = Column(String)
    country = Column(String)
    website = Column(String)

    # Outreach tracking
    emailed_at = Column(DateTime, nullable=True)
    followed_up_at = Column(DateTime, nullable=True)
    replied = Column(Boolean, default=False)
    meeting_booked = Column(Boolean, default=False)
    converted = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    agent = Column(String)          # "orchestrator" | "research" | "sales" | "mcp" | "reporter"
    action = Column(String)
    detail = Column(Text)
    success = Column(Boolean, default=True)


class DailyStats(Base):
    __tablename__ = "daily_stats"

    date = Column(String, primary_key=True)  # "YYYY-MM-DD"
    emails_sent = Column(Integer, default=0)
    followups_sent = Column(Integer, default=0)
    leads_fetched = Column(Integer, default=0)
    mcp_messages = Column(Integer, default=0)
    errors = Column(Integer, default=0)
    revenue_nok = Column(Float, default=0.0)


def init_db():
    """Opprett alle tabeller hvis de ikke finnes."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialisert")


# ---------------------------------------------------------------------------
# Lead-funksjoner
# ---------------------------------------------------------------------------

def save_leads(leads: List[Dict]) -> int:
    """
    Lagre leads til databasen. Ignorerer duplikater (basert på e-post).
    Returnerer antall faktisk lagrede leads.
    """
    saved = 0
    with SessionLocal() as db:
        for lead_data in leads:
            email = lead_data.get("email", "")
            if not email:
                continue
            existing = db.query(Lead).filter(Lead.email == email).first()
            if existing:
                continue
            lead = Lead(**{k: v for k, v in lead_data.items() if hasattr(Lead, k)})
            db.add(lead)
            saved += 1
        db.commit()
    return saved


def get_leads_needing_followup(days: int = 3) -> List[Dict]:
    """
    Hent leads som fikk e-post for minst {days} dager siden,
    ikke har svart og ikke har fått oppfølging ennå.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    with SessionLocal() as db:
        leads = db.query(Lead).filter(
            Lead.emailed_at <= cutoff,
            Lead.followed_up_at.is_(None),
            Lead.replied == False,
        ).all()
    result = []
    for l in leads:
        days_since = (datetime.utcnow() - l.emailed_at).days if l.emailed_at else days
        result.append({
            "id": l.id,
            "first_name": l.first_name,
            "last_name": l.last_name,
            "email": l.email,
            "company": l.company,
            "needs_followup": True,
            "days_since_first_email": days_since,
        })
    return result


def mark_lead_emailed(lead_id: str):
    with SessionLocal() as db:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.emailed_at = datetime.utcnow()
            db.commit()


def mark_lead_followed_up(lead_id: str):
    with SessionLocal() as db:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.followed_up_at = datetime.utcnow()
            db.commit()


def mark_lead_replied(email: str):
    with SessionLocal() as db:
        lead = db.query(Lead).filter(Lead.email == email).first()
        if lead:
            lead.replied = True
            db.commit()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_activity(agent: str, action: str, detail: str, success: bool = True):
    with SessionLocal() as db:
        entry = ActivityLog(agent=agent, action=action, detail=detail, success=success)
        db.add(entry)
        db.commit()


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------
init_db()
