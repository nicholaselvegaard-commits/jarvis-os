with open('/opt/nexus/server/mcp_server.py', 'r') as f:
    content = f.read()

# Add kg_cypher tool to MCP_TOOLS list
old_tool = '    {\n        "name": "kg_find_related",'
cypher_tool = '''    {
        "name": "kg_cypher",
        "description": "Run Cypher query against Kuzu graph DB (advanced graph queries).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "params": {"type": "object"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "kg_find_related",'''
content = content.replace(old_tool, cypher_tool, 1)

# Add cypher handler
old_handler = '    elif name == "kg_find_related":'
cypher_handler = '''    elif name == "kg_cypher":
        try:
            from memory.kuzu_graph import KuzuGraph
            kuzu_kg = KuzuGraph()
            rows = kuzu_kg.cypher(inputs["query"], params=inputs.get("params", {}))
            if not rows:
                return "No results."
            import json as _json
            return _json.dumps(rows[:20], ensure_ascii=False, indent=2)
        except Exception as e:
            return "Kuzu error: " + str(e)

    elif name == "kg_find_related":'''
content = content.replace(old_handler, cypher_handler, 1)

with open('/opt/nexus/server/mcp_server.py', 'w') as f:
    f.write(content)

import py_compile
py_compile.compile('/opt/nexus/server/mcp_server.py', doraise=True)
print('mcp_server.py: added kg_cypher tool, syntax OK')
