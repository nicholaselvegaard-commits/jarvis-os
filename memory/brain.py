"""
Brain — Unified Memory Interface for Jarvis.

Koordinerer alle memory-systemer:
  - smart_memory (SQLite conversations + reflections)
  - vector_memory (semantic search with embeddings)
  - knowledge_graph (entities + relations)
  - obsidian (markdown notes + vault)

Bruk:
    from memory.brain import Brain
    brain = Brain()

    # Lagre en memori (auto-ruter til riktig system)
    brain.remember("Lystpaa er en ny kunde, kontakt er Ole Nordmann", category="customer", importance=2)

    # Semantisk sok
    results = brain.recall("kunder med PLC-system")

    # Legg til entitet i graf
    brain.know("Lystpaa", type="company", attrs={"contact": "Ole Nordmann"})
    brain.relate("Lystpaa", "Jarvis", "er_kunde_av")

    # Skriv til Obsidian
    brain.note("Kunder/Lystpaa", "# Lystpaa\n\nStatus: Aktiv kunde")

    # Daglig rapport
    brain.log_daily("Opprettet 2 nye kundeemner via Apollo.")

    # Full kontekst for agent
    context = brain.get_context("Lystpaa")
"""
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class Brain:
    """
    Unified brain for Jarvis — coordinating all memory systems.
    """

    def __init__(self):
        self._vector = None
        self._kg = None
        self._obsidian = None
        self._smart = None

    # ── Lazy loaders ────────────────────────────────────────────

    @property
    def vector(self):
        if self._vector is None:
            try:
                from tools.vector_memory import VectorMemory
                self._vector = VectorMemory()
            except Exception as e:
                logger.warning(f"VectorMemory unavailable: {e}")
        return self._vector

    @property
    def kg(self):
        if self._kg is None:
            try:
                from memory.knowledge_graph import KnowledgeGraph
                self._kg = KnowledgeGraph()
            except Exception as e:
                logger.warning(f"KnowledgeGraph unavailable: {e}")
        return self._kg

    @property
    def obsidian(self):
        if self._obsidian is None:
            try:
                from memory.obsidian import ObsidianVault
                self._obsidian = ObsidianVault()
            except Exception as e:
                logger.warning(f"ObsidianVault unavailable: {e}")
        return self._obsidian

    @property
    def smart(self):
        if self._smart is None:
            try:
                from memory import smart_memory
                self._smart = smart_memory
            except Exception as e:
                logger.warning(f"SmartMemory unavailable: {e}")
        return self._smart

    # ── Core API ─────────────────────────────────────────────────

    def remember(self, content: str, category: str = "general", tags: list = None, importance: int = 1) -> dict:
        """
        Lagre informasjon i alle relevante memory-systemer.

        Returns dict with IDs from each system.
        """
        result = {}

        # Vector memory (semantic search)
        if self.vector:
            try:
                vid = self.vector.add(content, tags=tags or [], category=category, importance=importance)
                result["vector_id"] = vid
            except Exception as e:
                logger.warning(f"Vector remember failed: {e}")

        # Smart memory (structured)
        if self.smart:
            try:
                self.smart.save(category=category, content=content, tags=tags or [], priority=importance)
                result["smart"] = True
            except Exception as e:
                logger.warning(f"Smart remember failed: {e}")

        # Obsidian daily note for important memories
        if importance >= 2 and self.obsidian:
            try:
                timestamp = datetime.utcnow().strftime("%H:%M")
                self.obsidian.daily_note(f"**{timestamp}** [{category}] {content}")
                result["obsidian"] = True
            except Exception as e:
                logger.warning(f"Obsidian daily note failed: {e}")

        logger.info(f"Brain.remember: stored '{content[:60]}...' ({category}, importance={importance})")
        return result

    def recall(self, query: str, k: int = 5, category: str = None) -> list[dict]:
        """
        Semantisk sork på tvers av memory-systemer.
        Returnerer de mest relevante minnene.
        """
        results = []

        # Vector search (best semantic)
        if self.vector:
            try:
                hits = self.vector.search(query, k=k, category=category)
                for h in hits:
                    h["source"] = "vector"
                    results.append(h)
            except Exception as e:
                logger.warning(f"Vector recall failed: {e}")

        # KG search (entity-based)
        if self.kg:
            try:
                nodes = self.kg.search_nodes(query, limit=k)
                for n in nodes:
                    results.append({
                        "content": f"[{n['type']}] {n['label']}: {n['attrs']}",
                        "category": n["type"],
                        "source": "knowledge_graph",
                        "distance": 0.3,
                    })
            except Exception as e:
                logger.warning(f"KG recall failed: {e}")

        # Obsidian search (notes)
        if self.obsidian:
            try:
                notes = self.obsidian.search(query)[:3]
                for note in notes:
                    results.append({
                        "content": f"[note] {note['id']}: " + " | ".join(note.get("matches", [])),
                        "category": "note",
                        "source": "obsidian",
                        "distance": 0.4,
                    })
            except Exception as e:
                logger.warning(f"Obsidian recall failed: {e}")

        # Sort by relevance (lower distance = better)
        results.sort(key=lambda x: x.get("distance", 0.5))
        return results[:k]

    def know(self, entity_id: str, type: str = "concept", label: str = None, attrs: dict = None, importance: int = 1) -> str:
        """Legg til eller oppdater en entitet i knowledge graph."""
        if not self.kg:
            return entity_id
        node_id = self.kg.add_node(entity_id, type=type, label=label, attrs=attrs, importance=importance)

        # Auto-sync to Obsidian for important entities
        if importance >= 2 and self.obsidian:
            try:
                node = self.kg.get_node(node_id)
                related = self.kg.find_related(node_id)
                self.obsidian.from_kg_node(node, related)
            except Exception as e:
                logger.warning(f"KG->Obsidian sync failed: {e}")

        return node_id

    def relate(self, from_id: str, to_id: str, relation: str, confidence: float = 1.0) -> int:
        """Legg til en relasjon mellom to entiteter."""
        if not self.kg:
            return -1
        return self.kg.add_edge(from_id, to_id, relation, confidence=confidence)

    def note(self, note_id: str, content: str, tags: list = None) -> str:
        """Skriv et Obsidian-notat."""
        if not self.obsidian:
            return ""
        return self.obsidian.write(note_id, content, tags=tags)

    def read_note(self, note_id: str) -> Optional[str]:
        """Les et Obsidian-notat."""
        if not self.obsidian:
            return None
        return self.obsidian.read_content(note_id)

    def log_daily(self, text: str) -> str:
        """Legg til en logg-linje i dagens daglige notat."""
        if not self.obsidian:
            return ""
        return self.obsidian.daily_note(text)

    def get_context(self, topic: str, depth: int = 1) -> str:
        """
        Hent full kontekst om et tema for agent-bruk.
        Kombinerer KG, vector memory, og Obsidian.
        """
        lines = [f"## Kontekst: {topic}", ""]

        # Knowledge Graph
        if self.kg:
            try:
                node = self.kg.get_node(topic.lower().replace(" ", "_"))
                if not node:
                    nodes = self.kg.search_nodes(topic, limit=3)
                    node = nodes[0] if nodes else None
                if node:
                    lines.append(f"**Entitet**: {node['label']} ({node['type']})")
                    if node.get("attrs"):
                        for k, v in node["attrs"].items():
                            lines.append(f"- {k}: {v}")
                    related = self.kg.find_related(node["id"])
                    if related:
                        lines.append("\n**Relasjoner**:")
                        for r in related[:5]:
                            lines.append(f"- {r['direction']} {r['node']['label']} via {r['relation']}")
                    lines.append("")
            except Exception as e:
                logger.warning(f"KG context failed: {e}")

        # Semantic memories
        memories = self.recall(topic, k=5)
        if memories:
            lines.append("**Relevante minner**:")
            for m in memories:
                src = m.get("source", "?")
                lines.append(f"- [{src}] {m['content'][:150]}")
            lines.append("")

        # Obsidian notes
        if self.obsidian:
            try:
                notes = self.obsidian.search(topic)[:3]
                if notes:
                    lines.append("**Notater**:")
                    for n in notes:
                        lines.append(f"- {n['id']}: " + " | ".join(n.get("matches", [])))
            except Exception as e:
                logger.warning(f"Obsidian context failed: {e}")

        return "\n".join(lines)

    def status(self) -> dict:
        """Hent status for alle memory-systemer."""
        result = {}

        if self.kg:
            try:
                result["knowledge_graph"] = self.kg.summary()
            except Exception:
                result["knowledge_graph"] = "error"

        if self.vector:
            try:
                result["vector_memory"] = {"count": self.vector.count()}
            except Exception:
                result["vector_memory"] = "error"

        if self.obsidian:
            try:
                result["obsidian"] = self.obsidian.summary()
            except Exception:
                result["obsidian"] = "error"

        if self.smart:
            try:
                result["smart_memory"] = {"available": True}
            except Exception:
                result["smart_memory"] = "error"

        return result
