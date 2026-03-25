"""
NEXUS Knowledge Base — RAG over dine dokumenter og SOPs.

Indekserer tekstfiler, PDFs og markdown fra en konfigurerbar mappe.
NEXUS bruker dette til å svare med kontekst fra din egen business-kunnskap.

Standardmappe: /opt/nexus/knowledge/ (opprett og legg inn filer)
"""

import sqlite3
import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "knowledge.db"
KB_DIR = Path(os.getenv("KB_DIR", str(Path(__file__).parent.parent / "knowledge")))
CHUNK_SIZE = 500   # tegn per chunk
CHUNK_OVERLAP = 80


def _get_db() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH), timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _init():
    with _get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS kb_chunks (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                source    TEXT NOT NULL,
                chunk_idx INTEGER NOT NULL,
                content   TEXT NOT NULL,
                keywords  TEXT DEFAULT '',
                indexed_at TEXT DEFAULT (datetime('now'))
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_kb_source ON kb_chunks(source)")
        db.commit()


_init()


def _extract_keywords(text: str) -> str:
    """Ekstraher nøkkelord for søk."""
    stopwords = {"og", "er", "til", "for", "fra", "med", "på", "i", "av",
                 "the", "a", "is", "in", "of", "to", "and", "for", "with"}
    words = re.findall(r'\b[a-zA-ZæøåÆØÅ]{4,}\b', text.lower())
    return " ".join(w for w in set(words) if w not in stopwords)


def _chunk_text(text: str) -> List[str]:
    """Del tekst i overlappende chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _read_file(path: Path) -> str:
    """Les fil — støtter .txt, .md, .pdf."""
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md", ".csv"):
        return path.read_text(encoding="utf-8", errors="ignore")[:50000]
    elif suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return "\n".join(p.extract_text() or "" for p in reader.pages[:30])
        except ImportError:
            try:
                import pdfplumber
                with pdfplumber.open(str(path)) as pdf:
                    return "\n".join(p.extract_text() or "" for p in pdf.pages[:30])
            except Exception:
                return ""
    return ""


def index_directory(directory: Optional[Path] = None) -> Dict:
    """
    Indekser alle dokumenter i knowledge-mappen.
    Kjør dette etter å ha lagt til nye filer.
    """
    kb_path = directory or KB_DIR
    if not kb_path.exists():
        kb_path.mkdir(parents=True, exist_ok=True)
        return {"indexed": 0, "message": f"Mappe opprettet: {kb_path}. Legg inn filer og kjør igjen."}

    files = list(kb_path.glob("**/*.txt")) + \
            list(kb_path.glob("**/*.md")) + \
            list(kb_path.glob("**/*.pdf")) + \
            list(kb_path.glob("**/*.csv"))

    indexed = 0
    with _get_db() as db:
        for f in files:
            try:
                source = f.name
                # Sjekk om allerede indeksert (basert på filnavn)
                existing = db.execute(
                    "SELECT COUNT(*) FROM kb_chunks WHERE source=?", (source,)
                ).fetchone()[0]
                if existing > 0:
                    continue

                text = _read_file(f)
                if not text.strip():
                    continue

                chunks = _chunk_text(text)
                for i, chunk in enumerate(chunks):
                    kws = _extract_keywords(chunk)
                    db.execute(
                        "INSERT INTO kb_chunks (source, chunk_idx, content, keywords) VALUES (?,?,?,?)",
                        (source, i, chunk, kws),
                    )
                indexed += 1
            except Exception as e:
                logger.warning(f"Kunne ikke indeksere {f}: {e}")
        db.commit()

    return {"indexed": indexed, "total_files": len(files)}


def reindex(directory: Optional[Path] = None) -> Dict:
    """Slett alt og reindekser fra scratch."""
    with _get_db() as db:
        db.execute("DELETE FROM kb_chunks")
        db.commit()
    return index_directory(directory)


def query(question: str, top_k: int = 5, max_chars: int = 2000) -> str:
    """
    Søk kunnskapsbasen etter relevant kontekst.

    Args:
        question: Spørsmålet / brukermelding
        top_k:    Antall chunks å returnere
        max_chars: Maks tegn i output

    Returns:
        Formatert kontekst klar for LLM-injeksjon.
    """
    keywords = _extract_keywords(question).split()
    if not keywords:
        return ""

    try:
        with _get_db() as db:
            total = db.execute("SELECT COUNT(*) FROM kb_chunks").fetchone()[0]
            if total == 0:
                return ""

            rows = db.execute(
                "SELECT source, content, keywords FROM kb_chunks LIMIT 500"
            ).fetchall()
    except Exception as e:
        logger.warning(f"kb query feilet: {e}")
        return ""

    scored = []
    for row in rows:
        haystack = (row["content"] + " " + row["keywords"]).lower()
        score = sum(1 for kw in keywords if kw in haystack)
        if score > 0:
            scored.append((score, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    if not top:
        return ""

    parts = []
    used = 0
    for _, row in top:
        chunk = row["content"].strip()
        if used + len(chunk) > max_chars:
            chunk = chunk[:max_chars - used]
        parts.append(f"[{row['source']}]: {chunk}")
        used += len(chunk)
        if used >= max_chars:
            break

    return "\n\n[KUNNSKAPSBASE]:\n" + "\n\n".join(parts)


def add_text(content: str, source: str = "manual") -> int:
    """Legg til tekst direkte (uten fil)."""
    chunks = _chunk_text(content)
    with _get_db() as db:
        for i, chunk in enumerate(chunks):
            kws = _extract_keywords(chunk)
            db.execute(
                "INSERT INTO kb_chunks (source, chunk_idx, content, keywords) VALUES (?,?,?,?)",
                (source, i, chunk, kws),
            )
        db.commit()
    return len(chunks)


def stats() -> Dict:
    with _get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM kb_chunks").fetchone()[0]
        sources = db.execute(
            "SELECT source, COUNT(*) as n FROM kb_chunks GROUP BY source"
        ).fetchall()
    return {"total_chunks": total, "sources": {r["source"]: r["n"] for r in sources}}
