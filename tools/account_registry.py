"""
Account registry — Jarvis logs accounts he creates on behalf of Nicholas.

Nicholas's email: nicholas.elvegaard@gmail.com
Jarvis uses this email when signing up for platforms/tools he finds valuable.

Every account is logged here so Nicholas always knows what exists.
Stored at memory/accounts.json — readable by both Jarvis and Nicholas.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ACCOUNTS_PATH = Path("memory/accounts.json")
ACCOUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)

NICHOLAS_EMAIL = "nicholas.elvegaard@gmail.com"


def _load() -> list[dict]:
    if not ACCOUNTS_PATH.exists():
        return []
    try:
        return json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(entries: list[dict]) -> None:
    ACCOUNTS_PATH.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def log_account(
    website: str,
    reason: str,
    username: str,
    password: str,
    email: str = NICHOLAS_EMAIL,
    notes: str = "",
) -> dict:
    """
    Log a new account Jarvis created.

    Args:
        website: URL or name of the platform (e.g. "notion.so")
        reason: Why Jarvis created this account
        username: Username or handle used
        password: Password used
        email: Email used (default: Nicholas's email)
        notes: Any extra notes (API keys, plan tier, etc.)
    """
    entries = _load()

    # Check if already exists
    existing = [e for e in entries if e.get("website", "").lower() == website.lower()]
    if existing:
        logger.warning(f"Account for {website} already exists — updating")
        entries = [e for e in entries if e.get("website", "").lower() != website.lower()]

    entry = {
        "id": len(entries) + 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "website": website,
        "reason": reason,
        "email": email,
        "username": username,
        "password": password,
        "notes": notes,
    }
    entries.append(entry)
    _save(entries)
    logger.info(f"Account registry: logged {website} ({reason})")
    return {"status": "logged", "website": website}


def get_accounts(search: str | None = None) -> list[dict]:
    """Get all logged accounts, optionally filtered by search term."""
    entries = _load()
    if search:
        s = search.lower()
        entries = [e for e in entries if s in e.get("website", "").lower() or s in e.get("reason", "").lower()]
    return sorted(entries, key=lambda e: e.get("timestamp", ""), reverse=True)


def get_account(website: str) -> dict | None:
    """Get a specific account by website name."""
    for entry in _load():
        if entry.get("website", "").lower() == website.lower():
            return entry
    return None


def update_account(website: str, **kwargs) -> dict:
    """Update fields on an existing account."""
    entries = _load()
    for entry in entries:
        if entry.get("website", "").lower() == website.lower():
            entry.update(kwargs)
            entry["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save(entries)
            return {"status": "updated", "website": website}
    return {"status": "not_found"}


def delete_account(website: str) -> dict:
    """Remove an account from the registry."""
    entries = _load()
    before = len(entries)
    entries = [e for e in entries if e.get("website", "").lower() != website.lower()]
    _save(entries)
    return {"deleted": before - len(entries)}
