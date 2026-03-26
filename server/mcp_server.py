"""
Jarvis MCP HTTP Server — eksponerer Jarvis brain via HTTP.

Claude Desktop kan koble til dette som MCP server og bruke:
  - brain_remember / brain_context / brain_status
  - kg_add_node / kg_search / kg_find_related
  - obsidian_write / obsidian_read / obsidian_search
  - spawn_worker / delegate_task

Kjor: python3 /opt/nexus/server/mcp_server.py
Port: 8083
"""
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, "/opt/nexus")

from memory.brain import Brain
from workers.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

# Lazy-init
_brain = None
_orch = None


def get_brain():
    global _brain
    if _brain is None:
        _brain = Brain()
    return _brain


def get_orch():
    global _orch
    if _orch is None:
        _orch = Orchestrator()
    return _orch


# MCP tool definitions
MCP_TOOLS = [
    {
        "name": "brain_remember",
        "description": "Lagre viktig informasjon i Jarvis sin hukommelse (vector + KG + Obsidian)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Hva som skal huskes"},
                "category": {"type": "string", "default": "general"},
                "importance": {"type": "integer", "default": 1, "description": "1=normal, 2=viktig, 3=kritisk"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "brain_context",
        "description": "Hent full kontekst om et tema fra Jarvis sin hukommelse",
        "inputSchema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
    },
    {
        "name": "brain_status",
        "description": "Se status for Jarvis sine hukommelsessystemer",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "kg_add_node",
        "description": "Legg til en entitet i Jarvis sin knowledge graph",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "type": {"type": "string", "default": "concept"},
                "label": {"type": "string"},
                "attrs": {"type": "object"},
                "importance": {"type": "integer", "default": 1},
            },
            "required": ["node_id"],
        },
    },
    {
        "name": "kg_search",
        "description": "Sok etter entiteter i knowledge graph",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "type": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "kg_find_related",
        "description": "Finn relasjoner for en entitet i knowledge graph",
        "inputSchema": {
            "type": "object",
            "properties": {"node_id": {"type": "string"}},
            "required": ["node_id"],
        },
    },
    {
        "name": "obsidian_write",
        "description": "Skriv et notat til Jarvis sin Obsidian vault",
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "F.eks. Kunder/BedriftNavn"},
                "content": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["note_id", "content"],
        },
    },
    {
        "name": "obsidian_read",
        "description": "Les et notat fra Jarvis sin Obsidian vault",
        "inputSchema": {
            "type": "object",
            "properties": {"note_id": {"type": "string"}},
            "required": ["note_id"],
        },
    },
    {
        "name": "obsidian_search",
        "description": "Sok i Jarvis sin Obsidian vault",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "obsidian_list",
        "description": "List alle notater i vault",
        "inputSchema": {
            "type": "object",
            "properties": {"folder": {"type": "string"}},
        },
    },
    {
        "name": "spawn_worker",
        "description": "Spawn en spesialisert AI-arbeider (research/sales/content/code/analytics/memory)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "worker_type": {"type": "string"},
                "task": {"type": "string"},
                "context": {"type": "string", "default": ""},
            },
            "required": ["worker_type", "task"],
        },
    },
    {
        "name": "delegate_task",
        "description": "Deleger en sammensatt oppgave til orchestrator (planlegger og kjorer parallelle arbeidere)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "max_subtasks": {"type": "integer", "default": 5},
            },
            "required": ["task"],
        },
    },
]


def execute_tool(name: str, inputs: dict) -> str:
    brain = get_brain()
    orch = get_orch()

    if name == "brain_remember":
        result = brain.remember(inputs["content"], category=inputs.get("category", "general"), importance=inputs.get("importance", 1))
        return "Lagret: " + str(result)

    elif name == "brain_context":
        return brain.get_context(inputs["topic"])

    elif name == "brain_status":
        return json.dumps(brain.status(), ensure_ascii=False, indent=2)

    elif name == "kg_add_node":
        nid = brain.know(inputs["node_id"], type=inputs.get("type", "concept"), label=inputs.get("label"), attrs=inputs.get("attrs", {}), importance=inputs.get("importance", 1))
        return "Node lagret: " + nid

    elif name == "kg_search":
        if not brain.kg:
            return "KG ikke tilgjengelig"
        results = brain.kg.search_nodes(inputs["query"], type=inputs.get("type"), limit=10)
        if not results:
            return "Ingen noder funnet"
        return "\n".join([f"- {r['id']} ({r['type']}): {r['label']}" for r in results])

    elif name == "kg_find_related":
        if not brain.kg:
            return "KG ikke tilgjengelig"
        results = brain.kg.find_related(inputs["node_id"])
        if not results:
            return "Ingen relasjoner funnet"
        return "\n".join([f"- {r['direction']} {r['node']['label']} via {r['relation']}" for r in results])

    elif name == "obsidian_write":
        if not brain.obsidian:
            return "Obsidian ikke tilgjengelig"
        brain.obsidian.write(inputs["note_id"], inputs["content"], tags=inputs.get("tags", []))
        return "Notat skrevet: " + inputs["note_id"]

    elif name == "obsidian_read":
        if not brain.obsidian:
            return "Obsidian ikke tilgjengelig"
        content = brain.obsidian.read_content(inputs["note_id"])
        return content or "Notat ikke funnet"

    elif name == "obsidian_search":
        if not brain.obsidian:
            return "Obsidian ikke tilgjengelig"
        hits = brain.obsidian.search(inputs["query"])
        if not hits:
            return "Ingen notater funnet"
        return "\n".join([h["id"] + ": " + " | ".join(h.get("matches", [])[:2]) for h in hits[:10]])

    elif name == "obsidian_list":
        if not brain.obsidian:
            return "Obsidian ikke tilgjengelig"
        notes = brain.obsidian.list_notes(folder=inputs.get("folder"))
        return "\n".join([n["id"] for n in notes])

    elif name == "spawn_worker":
        result = orch.run_worker(inputs["worker_type"], inputs["task"], context=inputs.get("context", ""))
        status = "OK" if result.get("success") else "FEIL"
        return f"[{inputs['worker_type']}] {status} ({result.get('duration_ms',0)}ms):\n{result.get('result','')[:3000]}"

    elif name == "delegate_task":
        result = orch.delegate(inputs["task"], max_subtasks=inputs.get("max_subtasks", 5))
        plan_names = [s["worker"] + ": " + s["task"][:40] for s in result.get("plan", [])]
        return "Plan: " + ", ".join(plan_names) + "\n\n" + result.get("summary", "")

    return f"Ukjent verktoy: {name}"


class MCPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default logging

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_json({"status": "ok", "service": "jarvis-mcp"})
        elif self.path == "/tools":
            self.send_json({"tools": MCP_TOOLS})
        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or "{}")

        if self.path == "/call":
            name = body.get("name", "")
            inputs = body.get("inputs", body.get("arguments", {}))
            try:
                result = execute_tool(name, inputs)
                self.send_json({"result": result})
            except Exception as e:
                logger.error(f"MCP tool error {name}: {e}", exc_info=True)
                self.send_json({"error": str(e)}, 500)
        else:
            self.send_json({"error": "Not found"}, 404)


if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "8083"))
    server = HTTPServer(("0.0.0.0", port), MCPHandler)
    logger.info(f"Jarvis MCP server on port {port}")
    print(f"Jarvis MCP server running on http://0.0.0.0:{port}")
    print(f"Tools: {len(MCP_TOOLS)}")
    server.serve_forever()
