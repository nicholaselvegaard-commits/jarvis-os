"""
Vector database for semantic search over knowledge files and documents.
Uses ChromaDB (local, no API key needed).
Embeddings via OpenAI text-embedding-3-small (cheap) or sentence-transformers (free/local).
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

CHROMA_DIR = Path("memory/chroma")

try:
    import chromadb
    from chromadb.config import Settings
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False

_client = None
_collection = None


def _get_collection(collection_name: str = "knowledge"):
    global _client, _collection
    if not _CHROMA_AVAILABLE:
        raise ImportError("Install chromadb: pip install chromadb")

    if _client is None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    try:
        _collection = _client.get_collection(collection_name)
    except Exception:
        _collection = _client.create_collection(
            collection_name,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def add_document(doc_id: str, text: str, metadata: dict | None = None) -> None:
    """
    Add a document to the vector store.

    Args:
        doc_id: Unique document identifier
        text: Document text content
        metadata: Optional metadata dict
    """
    col = _get_collection()
    col.upsert(
        documents=[text],
        ids=[doc_id],
        metadatas=[metadata or {}],
    )
    logger.info(f"Vector DB: upserted {doc_id} ({len(text)} chars)")


def search(query: str, limit: int = 5, collection_name: str = "knowledge") -> list[dict]:
    """
    Semantic search over stored documents.

    Args:
        query: Natural language query
        limit: Max results
        collection_name: Which collection to search

    Returns:
        List of dicts with id, text, metadata, distance
    """
    col = _get_collection(collection_name)
    results = col.query(query_texts=[query], n_results=min(limit, col.count() or 1))

    output = []
    for i, doc_id in enumerate(results["ids"][0]):
        output.append({
            "id": doc_id,
            "text": results["documents"][0][i][:500],
            "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
            "distance": results["distances"][0][i] if results["distances"] else 0,
        })
    return output


def index_knowledge_files() -> int:
    """
    Index all files in knowledge/ into the vector store.
    Returns number of documents indexed.
    """
    knowledge_dir = Path("knowledge")
    if not knowledge_dir.exists():
        return 0

    count = 0
    for md_file in knowledge_dir.glob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        # Split into chunks of ~500 words
        chunks = _chunk_text(text, chunk_size=500)
        for i, chunk in enumerate(chunks):
            doc_id = f"{md_file.stem}_{i}"
            add_document(doc_id, chunk, {"source": md_file.name, "chunk": i})
            count += 1

    logger.info(f"Vector DB: indexed {count} chunks from knowledge/")
    return count


def _chunk_text(text: str, chunk_size: int = 500) -> list[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunks.append(" ".join(words[i:i + chunk_size]))
    return chunks
