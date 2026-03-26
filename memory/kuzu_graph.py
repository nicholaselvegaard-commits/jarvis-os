"""
Kuzu Knowledge Graph for Jarvis.

Oppgradering fra SQLite KG til KuzuDB — embedded Cypher-basert grafbase.
18x raskere innlesing, Cypher-spørringer, 80MB footprint (ingen server).

Kompatibel med memory/brain.py via samme API som KnowledgeGraph.

Bruk:
    from memory.kuzu_graph import KuzuGraph
    kg = KuzuGraph()
    kg.add_node("lystpaa", type="company", label="Lystpaa", attrs={"status": "kunde"})
    kg.add_edge("nicholas", "lystpaa", "er_kontakt_for")
    kg.find_related("lystpaa")
    kg.cypher("MATCH (n:Node) RETURN n.node_id, n.label LIMIT 10")
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path("/opt/nexus/memory/kuzu_graph.db")


class KuzuGraph:
    """
    Embedded Kuzu graph database — drop-in upgrade for KnowledgeGraph.
    Supports full Cypher queries.
    """

    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self):
        """Get a fresh connection. Kuzu allows one writer at a time."""
        import kuzu
        db = kuzu.Database(str(self.db_path))
        return kuzu.Connection(db)

    def _init_schema(self):
        """Create node and relationship tables if they don't exist."""
        try:
            self._get_conn().execute("""
                CREATE NODE TABLE IF NOT EXISTS Node (
                    node_id STRING PRIMARY KEY,
                    type STRING DEFAULT 'concept',
                    label STRING,
                    attrs STRING DEFAULT '{}',
                    created_at STRING,
                    updated_at STRING,
                    importance INT64 DEFAULT 1
                )
            """)
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.warning(f"Node table: {e}")

        try:
            self._get_conn().execute("""
                CREATE REL TABLE IF NOT EXISTS Relation (
                    FROM Node TO Node,
                    relation STRING,
                    attrs STRING DEFAULT '{}',
                    created_at STRING,
                    confidence DOUBLE DEFAULT 1.0
                )
            """)
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.warning(f"Relation table: {e}")

    def add_node(
        self,
        node_id: str,
        type: str = "concept",
        label: str = None,
        attrs: dict = None,
        importance: int = 1,
    ) -> str:
        """Add or update a node."""
        now = datetime.utcnow().isoformat()
        label = label or node_id
        attrs_json = json.dumps(attrs or {})

        try:
            # Check if exists
            result = self._get_conn().execute(
                "MATCH (n:Node {node_id: $nid}) RETURN n.node_id",
                {"nid": node_id}
            )
            rows = result.get_as_df()
            if len(rows) > 0:
                # Update
                old_result = self._get_conn().execute(
                    "MATCH (n:Node {node_id: $nid}) RETURN n.attrs",
                    {"nid": node_id}
                )
                old_df = old_result.get_as_df()
                old_attrs = {}
                if len(old_df) > 0:
                    try:
                        old_attrs = json.loads(old_df.iloc[0, 0] or "{}")
                    except Exception:
                        pass
                old_attrs.update(attrs or {})
                self._get_conn().execute(
                    "MATCH (n:Node {node_id: $nid}) SET n.label = $label, n.attrs = $attrs, n.updated_at = $now, n.importance = $imp",
                    {"nid": node_id, "label": label, "attrs": json.dumps(old_attrs), "now": now, "imp": importance}
                )
            else:
                # Insert
                self._get_conn().execute(
                    "CREATE (n:Node {node_id: $nid, type: $type, label: $label, attrs: $attrs, created_at: $now, updated_at: $now, importance: $imp})",
                    {"nid": node_id, "type": type, "label": label, "attrs": attrs_json, "now": now, "imp": importance}
                )
        except Exception as e:
            logger.error(f"KuzuGraph add_node error: {e}")

        return node_id

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        relation: str,
        attrs: dict = None,
        confidence: float = 1.0,
    ) -> bool:
        """Add a relationship between two nodes."""
        # Auto-create nodes
        if not self.get_node(from_id):
            self.add_node(from_id)
        if not self.get_node(to_id):
            self.add_node(to_id)

        now = datetime.utcnow().isoformat()
        attrs_json = json.dumps(attrs or {})

        try:
            # Check if relation exists
            result = self._get_conn().execute(
                "MATCH (a:Node {node_id: $fid})-[r:Relation {relation: $rel}]->(b:Node {node_id: $tid}) RETURN r.relation",
                {"fid": from_id, "tid": to_id, "rel": relation}
            )
            rows = result.get_as_df()
            if len(rows) > 0:
                logger.debug(f"KuzuGraph: edge already exists {from_id} -{relation}-> {to_id}")
                return True

            # Create relation
            self._get_conn().execute(
                "MATCH (a:Node {node_id: $fid}), (b:Node {node_id: $tid}) CREATE (a)-[:Relation {relation: $rel, attrs: $attrs, created_at: $now, confidence: $conf}]->(b)",
                {"fid": from_id, "tid": to_id, "rel": relation, "attrs": attrs_json, "now": now, "conf": confidence}
            )
            logger.debug(f"KuzuGraph edge: {from_id} --[{relation}]--> {to_id}")
            return True
        except Exception as e:
            logger.error(f"KuzuGraph add_edge error: {e}")
            return False

    def get_node(self, node_id: str) -> Optional[dict]:
        """Get a node by ID."""
        try:
            result = self._get_conn().execute(
                "MATCH (n:Node {node_id: $nid}) RETURN n.node_id, n.type, n.label, n.attrs, n.created_at, n.importance",
                {"nid": node_id}
            )
            df = result.get_as_df()
            if len(df) == 0:
                return None
            row = df.iloc[0]
            return {
                "id": row.iloc[0],
                "type": row.iloc[1],
                "label": row.iloc[2],
                "attrs": json.loads(row.iloc[3] or "{}"),
                "created_at": row.iloc[4],
                "importance": int(row.iloc[5]),
            }
        except Exception as e:
            logger.error(f"KuzuGraph get_node error: {e}")
            return None

    def find_related(self, node_id: str, relation: str = None, depth: int = 1) -> list:
        """Find all nodes related to a node."""
        results = []
        try:
            # Outgoing
            if relation:
                out_result = self._get_conn().execute(
                    "MATCH (a:Node {node_id: $nid})-[r:Relation {relation: $rel}]->(b:Node) RETURN b.node_id, b.type, b.label, b.attrs, b.importance, r.relation, r.confidence",
                    {"nid": node_id, "rel": relation}
                )
            else:
                out_result = self._get_conn().execute(
                    "MATCH (a:Node {node_id: $nid})-[r:Relation]->(b:Node) RETURN b.node_id, b.type, b.label, b.attrs, b.importance, r.relation, r.confidence",
                    {"nid": node_id}
                )
            out_df = out_result.get_as_df()
            for _, row in out_df.iterrows():
                results.append({
                    "node": {"id": row.iloc[0], "type": row.iloc[1], "label": row.iloc[2], "attrs": json.loads(row.iloc[3] or "{}"), "importance": int(row.iloc[4])},
                    "relation": row.iloc[5],
                    "direction": "→",
                    "confidence": float(row.iloc[6]),
                })

            # Incoming
            if relation:
                in_result = self._get_conn().execute(
                    "MATCH (a:Node)-[r:Relation {relation: $rel}]->(b:Node {node_id: $nid}) RETURN a.node_id, a.type, a.label, a.attrs, a.importance, r.relation, r.confidence",
                    {"nid": node_id, "rel": relation}
                )
            else:
                in_result = self._get_conn().execute(
                    "MATCH (a:Node)-[r:Relation]->(b:Node {node_id: $nid}) RETURN a.node_id, a.type, a.label, a.attrs, a.importance, r.relation, r.confidence",
                    {"nid": node_id}
                )
            in_df = in_result.get_as_df()
            for _, row in in_df.iterrows():
                results.append({
                    "node": {"id": row.iloc[0], "type": row.iloc[1], "label": row.iloc[2], "attrs": json.loads(row.iloc[3] or "{}"), "importance": int(row.iloc[4])},
                    "relation": row.iloc[5],
                    "direction": "←",
                    "confidence": float(row.iloc[6]),
                })
        except Exception as e:
            logger.error(f"KuzuGraph find_related error: {e}")
        return results

    def search_nodes(self, query: str, type: str = None, limit: int = 10) -> list:
        """Text search in node labels and attrs."""
        try:
            if type:
                result = self._get_conn().execute(
                    "MATCH (n:Node) WHERE n.type = $type AND (LOWER(n.label) CONTAINS LOWER($q) OR LOWER(n.attrs) CONTAINS LOWER($q)) RETURN n.node_id, n.type, n.label, n.attrs, n.importance ORDER BY n.importance DESC LIMIT $lim",
                    {"type": type, "q": query, "lim": limit}
                )
            else:
                result = self._get_conn().execute(
                    "MATCH (n:Node) WHERE LOWER(n.label) CONTAINS LOWER($q) OR LOWER(n.attrs) CONTAINS LOWER($q) RETURN n.node_id, n.type, n.label, n.attrs, n.importance ORDER BY n.importance DESC LIMIT $lim",
                    {"q": query, "lim": limit}
                )
            df = result.get_as_df()
            return [
                {"id": row.iloc[0], "type": row.iloc[1], "label": row.iloc[2], "attrs": json.loads(row.iloc[3] or "{}"), "importance": int(row.iloc[4])}
                for _, row in df.iterrows()
            ]
        except Exception as e:
            logger.error(f"KuzuGraph search error: {e}")
            return []

    def cypher(self, query: str, params: dict = None) -> list:
        """Execute a raw Cypher query. Returns list of dicts."""
        try:
            result = self._get_conn().execute(query, params or {})
            df = result.get_as_df()
            return df.to_dict(orient="records")
        except Exception as e:
            logger.error(f"KuzuGraph cypher error: {e}")
            return []

    def get_all_nodes(self, type: str = None, limit: int = 50) -> list:
        """Get all nodes, optionally filtered by type."""
        try:
            if type:
                result = self._get_conn().execute(
                    "MATCH (n:Node {type: $type}) RETURN n.node_id, n.type, n.label, n.attrs, n.importance ORDER BY n.importance DESC LIMIT $lim",
                    {"type": type, "lim": limit}
                )
            else:
                result = self._get_conn().execute(
                    "MATCH (n:Node) RETURN n.node_id, n.type, n.label, n.attrs, n.importance ORDER BY n.importance DESC LIMIT $lim",
                    {"lim": limit}
                )
            df = result.get_as_df()
            return [
                {"id": row.iloc[0], "type": row.iloc[1], "label": row.iloc[2], "attrs": json.loads(row.iloc[3] or "{}"), "importance": int(row.iloc[4])}
                for _, row in df.iterrows()
            ]
        except Exception as e:
            logger.error(f"KuzuGraph get_all error: {e}")
            return []

    def summary(self) -> dict:
        """Stats about the graph."""
        try:
            n_result = self._get_conn().execute("MATCH (n:Node) RETURN count(n)").get_as_df()
            e_result = self._get_conn().execute("MATCH ()-[r:Relation]->() RETURN count(r)").get_as_df()
            t_result = self._get_conn().execute("MATCH (n:Node) RETURN n.type, count(n) ORDER BY count(n) DESC").get_as_df()
            r_result = self._get_conn().execute("MATCH ()-[r:Relation]->() RETURN r.relation, count(r) ORDER BY count(r) DESC LIMIT 10").get_as_df()

            n_count = int(n_result.iloc[0, 0]) if len(n_result) > 0 else 0
            e_count = int(e_result.iloc[0, 0]) if len(e_result) > 0 else 0
            by_type = {row.iloc[0]: int(row.iloc[1]) for _, row in t_result.iterrows()}
            top_rels = {row.iloc[0]: int(row.iloc[1]) for _, row in r_result.iterrows()}

            return {
                "nodes": n_count,
                "edges": e_count,
                "by_type": by_type,
                "top_relations": top_rels,
                "db_type": "kuzu",
            }
        except Exception as e:
            return {"error": str(e), "db_type": "kuzu"}

    def migrate_from_sqlite(self, sqlite_kg):
        """Migrate data from SQLite KnowledgeGraph to Kuzu."""
        migrated_nodes = 0
        migrated_edges = 0

        # Migrate nodes
        try:
            rows = sqlite_kg.conn.execute(
                "SELECT id, type, label, attrs, created_at, importance FROM nodes"
            ).fetchall()
            for row in rows:
                self.add_node(row[0], type=row[1], label=row[2], attrs=json.loads(row[3] or "{}"), importance=row[5])
                migrated_nodes += 1
        except Exception as e:
            logger.error(f"Node migration error: {e}")

        # Migrate edges
        try:
            rows = sqlite_kg.conn.execute(
                "SELECT from_id, to_id, relation, attrs, confidence FROM edges"
            ).fetchall()
            for row in rows:
                self.add_edge(row[0], row[1], row[2], attrs=json.loads(row[3] or "{}"), confidence=row[4])
                migrated_edges += 1
        except Exception as e:
            logger.error(f"Edge migration error: {e}")

        logger.info(f"Migrated {migrated_nodes} nodes and {migrated_edges} edges from SQLite to Kuzu")
        return {"nodes": migrated_nodes, "edges": migrated_edges}

    def close(self):
        pass  # Kuzu handles cleanup automatically
