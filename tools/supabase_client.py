"""
Supabase client for Jarvis — write notes, accounts, activity to shared database.
Nicholas can read everything from AIOME dashboard on his phone.

Tables used:
  agent_notes   — shared notebook (Jarvis + MANUS + all agents)
  agent_events  — Jarvis's activity feed (what he did, found, built)

SQL to create tables (run in Supabase SQL editor):
  See bottom of this file.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")


def _headers() -> dict:
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _post(table: str, data: dict) -> dict:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        logger.warning("Supabase not configured, skipping sync")
        return {}
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        with httpx.Client(timeout=10) as client:
            r = client.post(url, headers=_headers(), json=data)
            r.raise_for_status()
            rows = r.json()
            return rows[0] if rows else {}
    except Exception as exc:
        logger.error(f"Supabase insert to {table} failed: {exc}")
        return {}


def _get(table: str, params: dict | None = None) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return []
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    default_params = {"order": "created_at.desc", "limit": "50"}
    if params:
        default_params.update(params)
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(url, headers=_headers(), params=default_params)
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        logger.error(f"Supabase select from {table} failed: {exc}")
        return []


def write_note(
    title: str,
    content: str,
    category: str = "other",
    agent_name: str = "jarvis",
) -> dict:
    """Write a note to the shared notebook. Visible to Nicholas on phone."""
    return _post("agent_notes", {
        "agent_name": agent_name,
        "category": category,
        "title": title,
        "content": content,
    })


def read_notes(agent_name: str | None = None, category: str | None = None, limit: int = 30) -> list[dict]:
    """Read notes from the shared notebook."""
    params: dict[str, Any] = {"limit": str(limit)}
    if agent_name:
        params["agent_name"] = f"eq.{agent_name}"
    if category:
        params["category"] = f"eq.{category}"
    return _get("agent_notes", params)


def log_event(
    agent_name: str,
    event_type: str,
    title: str,
    details: str = "",
) -> dict:
    """Log an activity event — shows in Nicholas's live feed."""
    return _post("agent_events", {
        "agent_name": agent_name,
        "event_type": event_type,
        "title": title,
        "details": details,
    })


def get_events(limit: int = 50) -> list[dict]:
    """Get recent agent activity events for the dashboard."""
    return _get("agent_events", {"limit": str(limit)})


# ─────────────────────────────────────────────
# SQL to run in Supabase SQL Editor:
# ─────────────────────────────────────────────
SQL_SETUP = """
-- Shared notebook for all agents
create table if not exists agent_notes (
  id bigserial primary key,
  agent_name text not null default 'jarvis',
  category text not null default 'other',
  title text not null,
  content text not null,
  created_at timestamptz default now()
);

-- Live activity feed
create table if not exists agent_events (
  id bigserial primary key,
  agent_name text not null default 'jarvis',
  event_type text not null,
  title text not null,
  details text default '',
  created_at timestamptz default now()
);

-- Allow public reads (dashboard reads without auth)
alter table agent_notes enable row level security;
alter table agent_events enable row level security;
create policy "public read notes" on agent_notes for select using (true);
create policy "public insert notes" on agent_notes for insert with check (true);
create policy "public read events" on agent_events for select using (true);
create policy "public insert events" on agent_events for insert with check (true);
"""
