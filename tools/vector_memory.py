"""
Vector memory for Jarvis — SQLite + sqlite-vec + sentence-transformers.

Semantisk søk: finn minner basert på meningslikhet, ikke bare nøkkelord.
Modell: all-MiniLM-L6-v2 (22MB, rask, gratis)

Bruk:
    from tools.vector_memory import VectorMemory
    vm = VectorMemory()
    vm.add("Kunden Lystpå betalte 5000 NOK for nettside", tags=["revenue", "customer"])
    results = vm.search("inntekter fra nettsider", k=5)
"""
import json
import logging
import sqlite3
import struct
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path("/opt/nexus/memory/vector_memory.db")

_encoder = None


def _get_encoder():
    global _encoder
    if _encoder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _encoder = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Embedding model loaded: all-MiniLM-L6-v2")
        except Exception as e:
            logger.error(f"Could not load embedding model: {e}")
            raise
    return _encoder


def _encode(text: str) -> bytes:
    model = _get_encoder()
    vec = model.encode(text, normalize_embeddings=True)
    return struct.pack(f"{len(vec)}f", *vec)


def _init_db() -> sqlite3.Connection:
    import sqlite_vec
    conn = sqlite3.connect(str(DB_PATH))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            tags TEXT DEFAULT '[]',
            category TEXT DEFAULT 'general',
            created_at TEXT NOT NULL,
            importance INTEGER DEFAULT 1
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec USING vec0(
            embedding float[384]
        );
    """)
    conn.commit()
    return conn


class VectorMemory:
    """Semantisk minnelager med SQLite + sqlite-vec."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.conn = _init_db()

    def add(
        self,
        content: str,
        tags: list[str] | None = None,
        category: str = "general",
        importance: int = 1,
    ) -> int:
        """
        Lagre et minne med embedding.

        Returns:
            memory_id
        """
        embedding = _encode(content)
        tags_json = json.dumps(tags or [])
        now = datetime.utcnow().isoformat()

        cur = self.conn.execute(
            "INSERT INTO memories (content, tags, category, created_at, importance) VALUES (?,?,?,?,?)",
            (content, tags_json, category, now, importance),
        )
        mem_id = cur.lastrowid

        self.conn.execute(
            "INSERT INTO memories_vec (rowid, embedding) VALUES (?,?)",
            (mem_id, embedding),
        )
        self.conn.commit()
        logger.debug(f"Vector memory added: id={mem_id}, category={category}")
        return mem_id

    def search(
        self,
        query: str,
        k: int = 5,
        category: Optional[str] = None,
    ) -> list[dict]:
        """
        Finn de k mest relevante minnene semantisk.

        Args:
            query:    Søketekst
            k:        Antall resultater
            category: Filtrer på kategori (valgfri)

        Returns:
            Liste med {content, tags, category, created_at, distance}
        """
        query_vec = _encode(query)

        if category:
            rows = self.conn.execute("""
                SELECT m.content, m.tags, m.category, m.created_at, v.distance
                FROM memories_vec v
                JOIN memories m ON m.id = v.rowid
                WHERE m.category = ?
                ORDER BY v.distance
                LIMIT ?
            """, (category, k)).fetchall()
        else:
            rows = self.conn.execute("""
                SELECT m.content, m.tags, m.category, m.created_at, v.distance
                FROM memories_vec v
                JOIN memories m ON m.id = v.rowid
                WHERE v.embedding MATCH ? AND k = ?
                ORDER BY v.distance
            """, (query_vec, k)).fetchall()

        return [
            {
                "content": row[0],
                "tags": json.loads(row[1]),
                "category": row[2],
                "created_at": row[3],
                "distance": row[4],
            }
            for row in rows
        ]

    def get_recent(self, limit: int = 20, category: Optional[str] = None) -> list[dict]:
        """Hent nyeste minner."""
        if category:
            rows = self.conn.execute(
                "SELECT content, tags, category, created_at FROM memories WHERE category=? ORDER BY created_at DESC LIMIT ?",
                (category, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT content, tags, category, created_at FROM memories ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [{"content": r[0], "tags": json.loads(r[1]), "category": r[2], "created_at": r[3]} for r in rows]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    def close(self):
        self.conn.close()
