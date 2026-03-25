"""
NEXUS Smart Memory — komprimert, kontekstuell hukommelse.

Strategi:
- Lagrer essens (≤120 tegn) + tags — ikke full tekst
- Auto-komprimerer etter 7 dager (sletter full_text, beholder essens)
- Injiserer maks 500 tokens relevant kontekst per samtale
- Scorer oppføringer etter keyword-match + recency
"""

import sqlite3
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "smart_memory.db"
MAX_TOKENS = 500
COMPRESS_AFTER_DAYS = 7
_CHARS_PER_TOKEN = 4  # 1 token ≈ 4 tegn (grov estimering)

_STOPWORDS = {
    "og", "er", "til", "for", "fra", "med", "på", "i", "av", "det", "den", "de",
    "en", "et", "ikke", "som", "har", "at", "vi", "jeg", "du", "han", "hun", "men",
    "the", "a", "an", "is", "in", "of", "to", "and", "for", "with", "that", "this",
}


# ── Intern helpers ────────────────────────────────────────────────────────────

def _tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _get_db() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c


def _init():
    with _get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS smart_memory (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                category    TEXT    NOT NULL,
                essence     TEXT    NOT NULL,
                full_text   TEXT,
                tags        TEXT    DEFAULT '[]',
                priority    INTEGER DEFAULT 1,
                created_at  TEXT    DEFAULT (datetime('now')),
                compressed  INTEGER DEFAULT 0
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_sm_cat ON smart_memory(category)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_sm_date ON smart_memory(created_at)")
        db.commit()


_init()


def _make_essence(text: str) -> str:
    """Komprimerer tekst til maks 120 tegn — kutter ved setningsgrense."""
    text = re.sub(r'\s+', ' ', text.strip())
    if len(text) <= 120:
        return text
    for punct in ['. ', '! ', '? ', ', ']:
        idx = text[:120].rfind(punct)
        if idx > 60:
            return text[:idx + 1].strip()
    return text[:117] + "..."


def _extract_tags(text: str) -> List[str]:
    """Ekstraher relevante nøkkelord (4+ tegn, ikke stopwords)."""
    words = re.findall(r'\b[a-zA-ZæøåÆØÅ]{4,}\b', text.lower())
    seen, tags = set(), []
    for w in words:
        if w not in _STOPWORDS and w not in seen:
            seen.add(w)
            tags.append(w)
        if len(tags) >= 12:
            break
    return tags


# ── Public API ─────────────────────────────────────────────────────────────────

def save(category: str, content: str, tags: Optional[List[str]] = None, priority: int = 1) -> int:
    """
    Lagre én hukommelse.

    Args:
        category: "lead"|"email"|"revenue"|"task"|"learning"|"chat"|"insight"
        content:  Fullt innhold (lagres komprimert)
        tags:     Nøkkelord for søk. Auto-ekstraherert hvis None.
        priority: 1=normal, 2=viktig, 3=kritisk

    Returns: id til lagret rad, eller -1 ved feil.
    """
    if not content or not content.strip():
        return -1
    tags = tags if tags is not None else _extract_tags(content)
    essence = _make_essence(content)
    try:
        with _get_db() as db:
            cur = db.execute(
                "INSERT INTO smart_memory (category, essence, full_text, tags, priority) VALUES (?,?,?,?,?)",
                (category, essence, content[:3000], json.dumps(tags), priority),
            )
            db.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error(f"smart_memory.save feilet: {e}")
        return -1


def save_learning(insight: str, category: str = "learning"):
    """Lagre én lærdom (snarvei)."""
    save(category, insight, priority=2)


def save_chat(role: str, content: str):
    """Lagre samtalemelding (brukes av conversation.py)."""
    if len(content.strip()) < 10:
        return
    save("chat", content, ["samtale", role], priority=1)


def get_context(user_message: str, max_tokens: int = MAX_TOKENS) -> str:
    """
    Hent relevant kontekst for user_message innenfor token-budsjettet.

    Scorer oppføringer:
        +1 per keyword-match i essens/tags
        +2 hvis opprettet siste 3 dager
        +1 hvis opprettet siste 7 dager
        × priority

    Returns:
        Formatert streng for injeksjon i system-prompt (tom hvis ingenting relevant).
    """
    keywords = _extract_tags(user_message)

    try:
        with _get_db() as db:
            rows = db.execute(
                """SELECT id, category, essence, tags, priority, created_at
                   FROM smart_memory
                   WHERE category != 'chat'
                   ORDER BY created_at DESC
                   LIMIT 300"""
            ).fetchall()
    except Exception as e:
        logger.warning(f"smart_memory.get_context feilet: {e}")
        return ""

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    scored = []

    for row in rows:
        tags = json.loads(row["tags"] or "[]")
        haystack = (row["essence"] + " " + " ".join(tags)).lower()

        kw_score = sum(1 for kw in keywords if kw in haystack)
        try:
            age = (now - datetime.fromisoformat(row["created_at"])).days
        except Exception:
            age = 999

        recency = 2 if age <= 3 else (1 if age <= 7 else 0)
        total = (kw_score + recency) * (row["priority"] or 1)

        if total > 0 or age == 0:
            scored.append((total, dict(row)))

    scored.sort(key=lambda x: x[0], reverse=True)

    lines = []
    used = 0
    for _, row in scored[:40]:
        text = row["essence"]
        t = _tokens(text)
        if used + t > max_tokens:
            break
        date_str = row["created_at"][:10]
        lines.append(f"[{date_str}][{row['category']}] {text}")
        used += t

    if not lines:
        return ""

    return "\n[NEXUS HUKOMMELSE — relevant kontekst]:\n" + "\n".join(lines)


def get_recent_chat(n: int = 8) -> List[dict]:
    """
    Hent siste N chat-meldinger (for samtalehistorikk til LLM).
    Returnerer [{"role": "user"|"assistant", "content": "..."}]
    """
    try:
        with _get_db() as db:
            rows = db.execute(
                """SELECT tags, essence, full_text, created_at
                   FROM smart_memory
                   WHERE category='chat'
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (n * 2,),
            ).fetchall()
    except Exception:
        return []

    result = []
    for row in reversed(rows):
        tags = json.loads(row["tags"] or "[]")
        role = "assistant" if "assistant" in tags else "user"
        text = row["full_text"] or row["essence"]
        result.append({"role": role, "content": text})
    return result[-n:]


def compress_old():
    """Komprimere oppføringer eldre enn 7 dager — slett full_text, beholder essens."""
    cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=COMPRESS_AFTER_DAYS)).isoformat()
    try:
        with _get_db() as db:
            db.execute(
                "UPDATE smart_memory SET full_text=NULL, compressed=1 WHERE created_at < ? AND compressed=0",
                (cutoff,),
            )
            db.commit()
    except Exception as e:
        logger.warning(f"compress_old feilet: {e}")


def stats() -> dict:
    """Statistikk om smart memory-basen."""
    try:
        with _get_db() as db:
            total = db.execute("SELECT COUNT(*) FROM smart_memory").fetchone()[0]
            compressed = db.execute("SELECT COUNT(*) FROM smart_memory WHERE compressed=1").fetchone()[0]
            by_cat = db.execute(
                "SELECT category, COUNT(*) as n FROM smart_memory GROUP BY category ORDER BY n DESC"
            ).fetchall()
        return {
            "total": total,
            "compressed": compressed,
            "by_category": {r["category"]: r["n"] for r in by_cat},
        }
    except Exception as e:
        return {"error": str(e)}
