"""
Jarvis's notebook — ideas, plans, observations.

Stored locally at memory/jarvis_notebook.json AND synced to Supabase
so Nicholas can read everything from AIOME dashboard on his phone.
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# Sync to Supabase silently — never crash the notebook if Supabase fails
def _sync_to_supabase(title: str, content: str, category: str) -> None:
    try:
        from tools.supabase_client import write_note
        write_note(title=title, content=content, category=category, agent_name="jarvis")
    except Exception as exc:
        logger.debug(f"Supabase sync skipped: {exc}")

NOTEBOOK_PATH = Path("memory/jarvis_notebook.json")
NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load() -> list[dict]:
    if not NOTEBOOK_PATH.exists():
        return []
    try:
        return json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(entries: list[dict]) -> None:
    NOTEBOOK_PATH.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def write_note(
    title: str,
    content: str,
    category: Literal["idea", "plan", "observation", "reminder", "other"] = "other",
) -> dict:
    """Write a note to Jarvis's private notebook."""
    entries = _load()
    entry = {
        "id": len(entries) + 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "title": title,
        "content": content,
    }
    _sync_to_supabase(title, content, category)
    entries.append(entry)
    _save(entries)
    logger.info(f"Notebook: wrote [{category}] {title!r}")
    return {"status": "saved", "id": entry["id"]}


def read_notes(category: str | None = None, limit: int = 20) -> list[dict]:
    """Read Jarvis's notebook entries, newest first."""
    entries = _load()
    if category:
        entries = [e for e in entries if e.get("category") == category]
    return list(reversed(entries))[:limit]


def search_notes(query: str) -> list[dict]:
    """Search notebook by keyword."""
    q = query.lower()
    return [
        e for e in _load()
        if q in e.get("title", "").lower() or q in e.get("content", "").lower()
    ]


def delete_note(note_id: int) -> dict:
    """Delete a note by ID."""
    entries = _load()
    before = len(entries)
    entries = [e for e in entries if e.get("id") != note_id]
    _save(entries)
    return {"deleted": before - len(entries)}
