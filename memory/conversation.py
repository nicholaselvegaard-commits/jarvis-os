"""
NEXUS Samtalehukommelse — lagrer Telegram-meldinger og laster de siste N.

Brukes av Telegram-boten for å gi NEXUS kontekst fra tidligere samtaler
uten å laste hele historikken og bruke opp API-credits.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

MEMORY_FILE = Path(__file__).parent / "nexus_chat_memory.json"
MAX_STORED = 100   # Maks meldinger lagret på fil
DEFAULT_LOAD = 8   # Antall meldinger som lastes inn som kontekst


def save_message(role: str, content: str):
    """Lagre én melding (user eller assistant) til hukommelsen."""
    messages = _load_all()
    messages.append({
        "role": role,
        "content": content[:2000],  # Ikke lagre ekstremt lange meldinger
        "timestamp": datetime.utcnow().isoformat(),
    })
    # Behold kun de siste MAX_STORED
    messages = messages[-MAX_STORED:]
    try:
        MEMORY_FILE.write_text(
            json.dumps(messages, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error(f"Kunne ikke lagre melding: {e}")

    # Speil til smart_memory for komprimert langtidslagring
    try:
        from memory.smart_memory import save_chat
        save_chat(role, content)
    except Exception:
        pass


def load_recent(n: int = DEFAULT_LOAD) -> list:
    """
    Last de siste N meldingene som LangChain/Anthropic-format:
    [{"role": "user"/"assistant", "content": "..."}]
    """
    messages = _load_all()
    recent = messages[-n:] if len(messages) > n else messages
    # Returner uten timestamp (LLM trenger det ikke)
    return [{"role": m["role"], "content": m["content"]} for m in recent]


def clear_memory():
    """Slett hele hukommelsen (bruk med forsiktighet)."""
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()
    logger.info("Samtalehukommelse slettet")


def _load_all() -> list:
    if not MEMORY_FILE.exists():
        return []
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Kunne ikke lese hukommelse: {e}")
        return []
