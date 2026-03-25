"""
Long-term memory manager.

Stores persistent info about Nicholas, his projects, customers, and
conversation summaries across bot restarts. Injected into every agent prompt.
"""
import copy
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LONG_TERM_FILE = Path("memory/long_term.json")

DEFAULT_MEMORY: dict = {
    "user": {
        "name": "Nicholas",
        "preferences": [],
        "notes": [],
    },
    "projects": [],
    "customers": [],
    "conversation_summaries": [],
}


def load_memory() -> dict:
    """Load long-term memory from disk. Returns defaults if file is missing or corrupt."""
    if LONG_TERM_FILE.exists():
        try:
            return json.loads(LONG_TERM_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            logger.warning("long_term.json was corrupt — resetting to defaults")
    return copy.deepcopy(DEFAULT_MEMORY)


def save_memory(memory: dict) -> None:
    """Persist long-term memory to disk."""
    LONG_TERM_FILE.parent.mkdir(parents=True, exist_ok=True)
    LONG_TERM_FILE.write_text(
        json.dumps(memory, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def update_memory(key: str, value: Any, action: str = "set") -> str:
    """
    Update a key in long-term memory.

    Args:
        key: Dot-notation path, e.g. "user.name", "projects", "customers"
        value: Value to set or append
        action: "set" to overwrite, "append" to add to a list

    Returns:
        Confirmation string
    """
    memory = load_memory()

    parts = key.split(".")
    target = memory
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            target[part] = {}
        target = target[part]

    final_key = parts[-1]
    if action == "append":
        lst = target.get(final_key, [])
        if not isinstance(lst, list):
            lst = [lst]
        lst.append(value)
        target[final_key] = lst
    else:
        target[final_key] = value

    save_memory(memory)
    logger.info(f"Memory updated: {key} ({action})")
    return f"Memory updated: {key}"


def add_conversation_summary(summary: str) -> None:
    """Append a conversation summary. Keeps the last 20 entries."""
    memory = load_memory()
    summaries = memory.setdefault("conversation_summaries", [])
    summaries.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
    })
    memory["conversation_summaries"] = summaries[-20:]
    save_memory(memory)


def get_context_block() -> str:
    """
    Return a formatted Markdown block of long-term memory for injection
    into the agent's system prompt.
    """
    memory = load_memory()
    sections: list[str] = []

    user = memory.get("user", {})
    notes = user.get("notes", [])
    if notes:
        sections.append("**Om Nicholas:**\n" + "\n".join(f"- {n}" for n in notes))

    projects = memory.get("projects", [])
    if projects:
        proj_lines = []
        for p in projects:
            if isinstance(p, dict):
                proj_lines.append(f"- **{p.get('name', '?')}**: {p.get('description', '')}")
            else:
                proj_lines.append(f"- {p}")
        sections.append("**Aktive prosjekter:**\n" + "\n".join(proj_lines))

    customers = memory.get("customers", [])
    if customers:
        cust_lines = []
        for c in customers:
            if isinstance(c, dict):
                cust_lines.append(f"- **{c.get('name', '?')}**: {c.get('notes', '')}")
            else:
                cust_lines.append(f"- {c}")
        sections.append("**Kunder / kontakter:**\n" + "\n".join(cust_lines))

    summaries = memory.get("conversation_summaries", [])
    if summaries:
        recent = summaries[-3:]
        sum_lines = [
            f"- [{s['timestamp'][:10]}] {s['summary']}"
            for s in recent
        ]
        sections.append("**Tidligere samtaler (siste 3):**\n" + "\n".join(sum_lines))

    if not sections:
        return ""

    return "## Langtidshukommelse\n\n" + "\n\n".join(sections) + "\n"
