with open('/opt/nexus/core/engine.py', 'r') as f:
    content = f.read()

# 1. Add new tool imports after vector_memory
old_imports = """    try:
        import tools.vector_memory as m; tools["vector_memory"] = m
    except Exception: tools["vector_memory"] = None
    return tools"""

new_imports = """    try:
        import tools.vector_memory as m; tools["vector_memory"] = m
    except Exception: tools["vector_memory"] = None
    try:
        import sys; sys.path.insert(0, "/opt/nexus")
        from memory.brain import Brain
        tools["brain"] = Brain()
    except Exception as e: tools["brain"] = None
    try:
        from workers.orchestrator import Orchestrator
        tools["orchestrator"] = Orchestrator()
    except Exception as e: tools["orchestrator"] = None
    return tools"""

content = content.replace(old_imports, new_imports)

# 2. Add new tool schemas before minimax_chat schema
new_schemas = """    {
        "name": "kg_add_node",
        "description": "Legg til eller oppdater en entitet i Jarvis sin knowledge graph.",
        "input_schema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "type": {"type": "string", "default": "concept", "description": "person|company|product|concept|place|tool"},
                "label": {"type": "string"},
                "attrs": {"type": "object"},
                "importance": {"type": "integer", "default": 1},
            },
            "required": ["node_id"],
        },
    },
    {
        "name": "kg_add_edge",
        "description": "Legg til en relasjon mellom to entiteter i knowledge graph.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_id": {"type": "string"},
                "to_id": {"type": "string"},
                "relation": {"type": "string"},
                "confidence": {"type": "number", "default": 1.0},
            },
            "required": ["from_id", "to_id", "relation"],
        },
    },
    {
        "name": "kg_find_related",
        "description": "Finn alle entiteter relatert til en node.",
        "input_schema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "relation": {"type": "string"},
            },
            "required": ["node_id"],
        },
    },
    {
        "name": "obsidian_write",
        "description": "Skriv et Markdown-notat til Jarvis sin Obsidian-vault.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "Eks: Kunder/Lystpaa"},
                "content": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}, "default": []},
            },
            "required": ["note_id", "content"],
        },
    },
    {
        "name": "obsidian_read",
        "description": "Les et notat fra Jarvis sin Obsidian-vault.",
        "input_schema": {
            "type": "object",
            "properties": {"note_id": {"type": "string"}},
            "required": ["note_id"],
        },
    },
    {
        "name": "obsidian_search",
        "description": "Sok etter notater i Obsidian-vault.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "brain_remember",
        "description": "Lagre viktig informasjon i alle Jarvis sine hukommelses-systemer (vector, KG, Obsidian daglig notat).",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "category": {"type": "string", "default": "general"},
                "importance": {"type": "integer", "default": 1, "description": "1=normal, 2=viktig, 3=kritisk"},
                "tags": {"type": "array", "items": {"type": "string"}, "default": []},
            },
            "required": ["content"],
        },
    },
    {
        "name": "brain_context",
        "description": "Hent full kontekst om et tema fra alle Jarvis sine hukommelsessystemer.",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
    },
    {
        "name": "spawn_worker",
        "description": "Spawn en spesialisert AI-arbeider. Typer: research, sales, content, code, analytics, memory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "worker_type": {"type": "string", "description": "research|sales|content|code|analytics|memory"},
                "task": {"type": "string"},
                "context": {"type": "string", "default": ""},
            },
            "required": ["worker_type", "task"],
        },
    },
    {
        "name": "delegate_task",
        "description": "Deleger en sammensatt oppgave til Orchestrator som planlegger og kjorer riktige arbeidere parallelt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "max_subtasks": {"type": "integer", "default": 5},
            },
            "required": ["task"],
        },
    },
"""

insert_before = '    {\n        "name": "minimax_chat",'
content = content.replace(insert_before, new_schemas + insert_before, 1)

# 3. Add handlers before minimax_chat handler
new_handlers = """
        elif name == "kg_add_node":
            if not t.get("brain"):
                return "Brain ikke tilgjengelig."
            try:
                nid = t["brain"].know(inputs["node_id"], type=inputs.get("type","concept"), label=inputs.get("label"), attrs=inputs.get("attrs",{}), importance=inputs.get("importance",1))
                return "KG node: " + nid
            except Exception as e:
                return "KG feil: " + str(e)

        elif name == "kg_add_edge":
            if not t.get("brain"):
                return "Brain ikke tilgjengelig."
            try:
                eid = t["brain"].relate(inputs["from_id"], inputs["to_id"], inputs["relation"], confidence=inputs.get("confidence",1.0))
                return "KG edge ID: " + str(eid)
            except Exception as e:
                return "KG feil: " + str(e)

        elif name == "kg_find_related":
            if not t.get("brain") or not t["brain"].kg:
                return "KG ikke tilgjengelig."
            try:
                results = t["brain"].kg.find_related(inputs["node_id"], relation=inputs.get("relation"))
                if not results:
                    return "Ingen relasjoner funnet for: " + inputs["node_id"]
                lines = [r["direction"] + " " + r["node"]["label"] + " via " + r["relation"] for r in results]
                return chr(10).join(lines)
            except Exception as e:
                return "KG feil: " + str(e)

        elif name == "obsidian_write":
            if not t.get("brain") or not t["brain"].obsidian:
                return "Obsidian ikke tilgjengelig."
            try:
                t["brain"].obsidian.write(inputs["note_id"], inputs["content"], tags=inputs.get("tags",[]))
                return "Notat skrevet: " + inputs["note_id"]
            except Exception as e:
                return "Obsidian feil: " + str(e)

        elif name == "obsidian_read":
            if not t.get("brain") or not t["brain"].obsidian:
                return "Obsidian ikke tilgjengelig."
            try:
                note_content = t["brain"].obsidian.read_content(inputs["note_id"])
                if not note_content:
                    return "Notat ikke funnet: " + inputs["note_id"]
                return note_content[:3000]
            except Exception as e:
                return "Obsidian feil: " + str(e)

        elif name == "obsidian_search":
            if not t.get("brain") or not t["brain"].obsidian:
                return "Obsidian ikke tilgjengelig."
            try:
                hits = t["brain"].obsidian.search(inputs["query"])
                if not hits:
                    return "Ingen notater funnet for: " + inputs["query"]
                lines = [n["id"] + ": " + " | ".join(n.get("matches",[])[:2]) for n in hits[:5]]
                return chr(10).join(lines)
            except Exception as e:
                return "Obsidian feil: " + str(e)

        elif name == "brain_remember":
            if not t.get("brain"):
                return "Brain ikke tilgjengelig."
            try:
                result = t["brain"].remember(inputs["content"], category=inputs.get("category","general"), importance=inputs.get("importance",1), tags=inputs.get("tags",[]))
                return "Lagret i brain: " + str(result)
            except Exception as e:
                return "Brain feil: " + str(e)

        elif name == "brain_context":
            if not t.get("brain"):
                return "Brain ikke tilgjengelig."
            try:
                return t["brain"].get_context(inputs["topic"])
            except Exception as e:
                return "Brain feil: " + str(e)

        elif name == "spawn_worker":
            if not t.get("orchestrator"):
                return "Orchestrator ikke tilgjengelig."
            try:
                result = t["orchestrator"].run_worker(inputs["worker_type"], inputs["task"], context=inputs.get("context",""))
                status = "OK" if result.get("success") else "FEIL"
                return "[" + inputs["worker_type"] + "] " + status + " (" + str(result.get("duration_ms",0)) + "ms):" + chr(10) + result.get("result","")[:2000]
            except Exception as e:
                return "Worker feil: " + str(e)

        elif name == "delegate_task":
            if not t.get("orchestrator"):
                return "Orchestrator ikke tilgjengelig."
            try:
                result = t["orchestrator"].delegate(inputs["task"], max_subtasks=inputs.get("max_subtasks",5))
                plan_names = [s["worker"] + ":" + s["task"][:40] for s in result.get("plan",[])]
                output = "Plan: " + ", ".join(plan_names) + chr(10) + chr(10)
                output += "Sammendrag:" + chr(10) + result.get("summary","")
                output += chr(10) + chr(10) + "(" + str(result.get("workers_used",0)) + " arbeidere, " + str(result.get("duration_ms",0)) + "ms, " + str(result.get("total_tokens",0)) + " tokens)"
                return output
            except Exception as e:
                return "Delegate feil: " + str(e)

"""

insert_handler_before = '        elif name == "minimax_chat":'
content = content.replace(insert_handler_before, new_handlers + insert_handler_before, 1)

with open('/opt/nexus/core/engine.py', 'w') as f:
    f.write(content)
print("engine.py updated with brain + worker tools")
