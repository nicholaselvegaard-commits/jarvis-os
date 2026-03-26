"""
Knowledge Graph for Jarvis — SQLite-based.

Jarvis kan lagre kunnskap som NODER og KANTER:
  Node: en entitet (person, bedrift, konsept, produkt, sted)
  Edge: en relasjon mellom to noder

Eksempel:
  Lystpaa (bedrift) —[er_kunde_av]→ Jarvis (agent)
  Nicholas (person) —[eier]→ Jarvis (agent)
  ChatGPT Prompt Pack (produkt) —[selges_for]→ 99 NOK (pris)

Kunnskap bygges opp over tid og kan søkes semantisk.

Bruk:
    from memory.knowledge_graph import KnowledgeGraph
    kg = KnowledgeGraph()
    kg.add_node("Lystpaa", type="customer", attrs={"revenue": 0, "contact": "ukjent"})
    kg.add_edge("Lystpaa", "Jarvis", relation="er_kunde_av")
    kg.find_related("Lystpaa")  # → alle noder relatert til Lystpaa
"""
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path("/opt/nexus/memory/knowledge_graph.db")


class KnowledgeGraph:
    """
    Lett kunnskapsgraf basert på SQLite.
    Noder = entiteter, Kanter = relasjoner.
    """

    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL DEFAULT 'concept',
                label TEXT NOT NULL,
                attrs TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                importance INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                attrs TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                FOREIGN KEY (from_id) REFERENCES nodes(id),
                FOREIGN KEY (to_id) REFERENCES nodes(id)
            );
            CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_id);
            CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id);
            CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);
            CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
        """)
        self.conn.commit()

    def add_node(
        self,
        node_id: str,
        type: str = "concept",
        label: Optional[str] = None,
        attrs: Optional[dict] = None,
        importance: int = 1,
    ) -> str:
        """
        Legg til eller oppdater en node.

        Args:
            node_id:    Unik ID (f.eks. "lystpaa", "nicholas", "plc_platform")
            type:       person | company | product | concept | place | event | tool
            label:      Menneskelig navn (default = node_id)
            attrs:      Ekstra data som dict
            importance: 1=normal, 2=viktig, 3=kritisk

        Returns:
            node_id
        """
        now = datetime.utcnow().isoformat()
        label = label or node_id
        attrs_json = json.dumps(attrs or {})

        # Upsert
        existing = self.conn.execute("SELECT id, attrs FROM nodes WHERE id = ?", (node_id,)).fetchone()
        if existing:
            # Merge attrs
            old_attrs = json.loads(existing[1])
            old_attrs.update(attrs or {})
            self.conn.execute(
                "UPDATE nodes SET label=?, attrs=?, updated_at=?, importance=? WHERE id=?",
                (label, json.dumps(old_attrs), now, importance, node_id)
            )
        else:
            self.conn.execute(
                "INSERT INTO nodes (id, type, label, attrs, created_at, updated_at, importance) VALUES (?,?,?,?,?,?,?)",
                (node_id, type, label, attrs_json, now, now, importance)
            )
        self.conn.commit()
        logger.debug(f"KG node upserted: {node_id} ({type})")
        return node_id

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        relation: str,
        attrs: Optional[dict] = None,
        confidence: float = 1.0,
    ) -> int:
        """
        Legg til en relasjon mellom to noder.

        Args:
            from_id:    Kilde-node ID
            to_id:      Mål-node ID
            relation:   Relasjonstype (f.eks. "er_kunde_av", "eier", "jobber_for", "bruker")
            attrs:      Ekstra data
            confidence: 0.0-1.0, hvor sikker er vi på denne relasjonen

        Returns:
            edge_id
        """
        # Auto-create nodes if they don't exist
        if not self.get_node(from_id):
            self.add_node(from_id)
        if not self.get_node(to_id):
            self.add_node(to_id)

        now = datetime.utcnow().isoformat()
        # Check if edge already exists
        existing = self.conn.execute(
            "SELECT id FROM edges WHERE from_id=? AND to_id=? AND relation=?",
            (from_id, to_id, relation)
        ).fetchone()

        if existing:
            self.conn.execute(
                "UPDATE edges SET attrs=?, confidence=? WHERE id=?",
                (json.dumps(attrs or {}), confidence, existing[0])
            )
            self.conn.commit()
            return existing[0]

        cur = self.conn.execute(
            "INSERT INTO edges (from_id, to_id, relation, attrs, created_at, confidence) VALUES (?,?,?,?,?,?)",
            (from_id, to_id, relation, json.dumps(attrs or {}), now, confidence)
        )
        self.conn.commit()
        logger.debug(f"KG edge: {from_id} --[{relation}]--> {to_id}")
        return cur.lastrowid

    def get_node(self, node_id: str) -> Optional[dict]:
        """Hent en node med alle detaljer."""
        row = self.conn.execute(
            "SELECT id, type, label, attrs, created_at, importance FROM nodes WHERE id=?", (node_id,)
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "type": row[1], "label": row[2], "attrs": json.loads(row[3]),
                "created_at": row[4], "importance": row[5]}

    def find_related(
        self,
        node_id: str,
        relation: Optional[str] = None,
        depth: int = 1,
    ) -> list[dict]:
        """
        Finn alle noder relatert til en node.

        Args:
            node_id:  Startnode
            relation: Filtrer på relasjonstype (None = alle)
            depth:    Søkedybde (1 = direkte koblinger)

        Returns:
            [{node, relation, direction}]
        """
        results = []

        # Outgoing edges
        if relation:
            rows = self.conn.execute(
                "SELECT to_id, relation, confidence FROM edges WHERE from_id=? AND relation=?",
                (node_id, relation)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT to_id, relation, confidence FROM edges WHERE from_id=?", (node_id,)
            ).fetchall()

        for to_id, rel, conf in rows:
            node = self.get_node(to_id)
            if node:
                results.append({"node": node, "relation": rel, "direction": "→", "confidence": conf})

        # Incoming edges
        if relation:
            in_rows = self.conn.execute(
                "SELECT from_id, relation, confidence FROM edges WHERE to_id=? AND relation=?",
                (node_id, relation)
            ).fetchall()
        else:
            in_rows = self.conn.execute(
                "SELECT from_id, relation, confidence FROM edges WHERE to_id=?", (node_id,)
            ).fetchall()

        for from_id, rel, conf in in_rows:
            node = self.get_node(from_id)
            if node:
                results.append({"node": node, "relation": rel, "direction": "←", "confidence": conf})

        return results

    def search_nodes(self, query: str, type: Optional[str] = None, limit: int = 10) -> list[dict]:
        """Tekstsøk i node-labels og attrs."""
        if type:
            rows = self.conn.execute(
                "SELECT id, type, label, attrs, importance FROM nodes WHERE type=? AND (label LIKE ? OR attrs LIKE ?) ORDER BY importance DESC LIMIT ?",
                (type, f"%{query}%", f"%{query}%", limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, type, label, attrs, importance FROM nodes WHERE label LIKE ? OR attrs LIKE ? ORDER BY importance DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", limit)
            ).fetchall()
        return [{"id": r[0], "type": r[1], "label": r[2], "attrs": json.loads(r[3]), "importance": r[4]} for r in rows]

    def get_all_nodes(self, type: Optional[str] = None, limit: int = 50) -> list[dict]:
        if type:
            rows = self.conn.execute(
                "SELECT id, type, label, attrs, importance FROM nodes WHERE type=? ORDER BY importance DESC, updated_at DESC LIMIT ?",
                (type, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, type, label, attrs, importance FROM nodes ORDER BY importance DESC, updated_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [{"id": r[0], "type": r[1], "label": r[2], "attrs": json.loads(r[3]), "importance": r[4]} for r in rows]

    def summary(self) -> dict:
        """Stats om kunnskapsgrafen."""
        nodes = self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edges = self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        types = self.conn.execute("SELECT type, COUNT(*) FROM nodes GROUP BY type").fetchall()
        relations = self.conn.execute("SELECT relation, COUNT(*) FROM edges GROUP BY relation ORDER BY COUNT(*) DESC LIMIT 10").fetchall()
        return {
            "nodes": nodes, "edges": edges,
            "by_type": dict(types),
            "top_relations": dict(relations),
        }

    def to_markdown(self, node_id: str) -> str:
        """Eksporter en node og dens relasjoner som Markdown (Obsidian-format)."""
        node = self.get_node(node_id)
        if not node:
            return f"# {node_id}\n(ukjent node)"

        related = self.find_related(node_id)
        lines = [
            f"# {node['label']}",
            f"type:: {node['type']}",
            f"importance:: {node['importance']}",
            f"created:: {node['created_at'][:10]}",
            "",
        ]
        if node['attrs']:
            lines.append("## Egenskaper")
            for k, v in node['attrs'].items():
                lines.append(f"- **{k}**: {v}")
            lines.append("")

        if related:
            lines.append("## Relasjoner")
            for r in related:
                arrow = r['direction']
                rel = r['relation']
                label = r['node']['label']
                lines.append(f"- {arrow} [[{label}]] via *{rel}*")

        return "\n".join(lines)

    def close(self):
        self.conn.close()
