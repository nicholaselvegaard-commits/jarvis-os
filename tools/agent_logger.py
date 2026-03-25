"""
AgentLogger — logs all sub-agent activity to Supabase + local fallback.

Writes to:
1. Supabase agent_events table (visible on AIOME dashboard)
2. memory/agent_activity.jsonl (local fallback)

Curios bot reads from Supabase to answer "what's everyone doing?"
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

LOCAL_LOG = Path("memory/agent_activity.jsonl")


async def log_event(
    agent_name: str,
    event_type: str,
    title: str,
    details: str = "",
) -> None:
    """
    Log an agent event to Supabase + local file.

    Args:
        agent_name: e.g. "sales", "research", "curios"
        event_type: "task" | "error" | "alert" | "status"
        title: Short description of what happened
        details: Longer result or context
    """
    payload = {
        "agent_name": agent_name,
        "event_type": event_type,
        "title": title[:200],
        "details": details[:1000],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Write to local log first (never fails)
    _write_local(payload)

    # Try Supabase
    try:
        await _write_supabase(payload)
    except Exception as e:
        logger.debug(f"agent_logger: Supabase write failed (local log OK): {e}")


def _write_local(payload: dict) -> None:
    try:
        LOCAL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOCAL_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        # Keep last 500 lines
        lines = LOCAL_LOG.read_text(encoding="utf-8").splitlines()
        if len(lines) > 500:
            LOCAL_LOG.write_text("\n".join(lines[-500:]) + "\n", encoding="utf-8")
    except Exception as e:
        logger.warning(f"agent_logger local write failed: {e}")


async def _write_supabase(payload: dict) -> None:
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return

    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(
            f"{url}/rest/v1/agent_events",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=payload,
        )
        r.raise_for_status()


def get_recent_events(agent_name: str | None = None, limit: int = 20) -> list[dict]:
    """
    Read recent events from local log.
    Curios uses this to summarize what agents have been doing.
    """
    if not LOCAL_LOG.exists():
        return []
    try:
        lines = LOCAL_LOG.read_text(encoding="utf-8").splitlines()
        events = []
        for line in reversed(lines[-200:]):
            try:
                e = json.loads(line)
                if agent_name is None or e.get("agent_name") == agent_name:
                    events.append(e)
                    if len(events) >= limit:
                        break
            except Exception:
                continue
        return events
    except Exception:
        return []


def get_agent_last_action(agent_name: str) -> dict | None:
    """Get the most recent event for a specific agent."""
    events = get_recent_events(agent_name=agent_name, limit=1)
    return events[0] if events else None


def get_empire_status() -> dict:
    """
    Full status snapshot of all agents for Curios.
    Returns dict: agent_name → {last_action, last_seen, status}
    """
    from agents import REGISTRY

    status = {}
    for name in REGISTRY:
        last = get_agent_last_action(name)
        if last:
            status[name] = {
                "last_action": last.get("title", ""),
                "last_seen": last.get("created_at", ""),
                "type": last.get("event_type", ""),
                "details": last.get("details", "")[:100],
            }
        else:
            status[name] = {
                "last_action": "Never run",
                "last_seen": None,
                "type": "idle",
                "details": "",
            }
    return status
