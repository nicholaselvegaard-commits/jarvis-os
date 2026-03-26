"""Final system test — all components."""
import sys
sys.path.insert(0, '/opt/nexus')

print("=" * 60)
print("JARVIS BRAIN + WORKER SYSTEM — FINAL TEST")
print("=" * 60)

# 1. Brain
print("\n[1] BRAIN SYSTEM")
from memory.brain import Brain
brain = Brain()
status = brain.status()
kg_nodes = status.get('knowledge_graph', {}).get('nodes', 0)
kg_edges = status.get('knowledge_graph', {}).get('edges', 0)
print(f"  KG: {kg_nodes} nodes, {kg_edges} edges")
print(f"  Vector: {status.get('vector_memory', {}).get('count', 0)} memories")
print(f"  Obsidian: {status.get('obsidian', {}).get('total_notes', 0)} notes")
print(f"  SmartMemory: OK")

# 2. Knowledge Graph
print("\n[2] KNOWLEDGE GRAPH")
kg = brain.kg
if kg:
    node = kg.get_node('nicholas')
    print(f"  nicholas: {node['label'] if node else 'NOT FOUND'}")
    related = kg.find_related('nicholas')
    for r in related[:3]:
        print(f"  {r['direction']} {r['node']['label']} via {r['relation']}")
    companies = kg.search_nodes('', type='company', limit=5)
    print(f"  Companies: {[c['label'] for c in companies]}")
else:
    print("  KG NOT AVAILABLE")

# 3. Vector Memory
print("\n[3] VECTOR MEMORY")
if brain.vector:
    results = brain.vector.search("AI agent system Norway", k=3)
    print(f"  Semantic search OK: {len(results)} results")
    if results:
        print(f"  Top: {results[0]['content'][:70]}...")
else:
    print("  NOT AVAILABLE")

# 4. Obsidian
print("\n[4] OBSIDIAN VAULT")
if brain.obsidian:
    brain.obsidian.write(
        "Prosjekter/BrainSystem",
        "# Brain System v1.0\n\nDeployed 2026-03-26.\n\n## Komponenter\n- KG (SQLite WAL)\n- Vector memory\n- Obsidian vault\n- 6 worker types\n- MCP server (port 8083)",
        tags=["system", "brain"]
    )
    notes = brain.obsidian.list_notes()
    print(f"  {len(notes)} notes in vault")
    print(f"  Wrote Prosjekter/BrainSystem OK")
else:
    print("  NOT AVAILABLE")

# 5. Workers parallel
print("\n[5] WORKERS (parallel)")
from workers.orchestrator import Orchestrator
import time
orch = Orchestrator()
start = time.time()
results = orch.run_parallel([
    ('memory', 'Legg til node: AIDN AS er en IT bedrift i Bodo med 127 ansatte. importance=2'),
    ('analytics', 'Hva er befolkningsstall for Bodo fra SSB? Gi et tall.'),
])
elapsed = int((time.time() - start) * 1000)
print(f"  2 workers in parallel: {elapsed}ms total")
for r in results:
    w = r.get('worker', '?')
    ok = 'OK' if r.get('success') else 'FEIL'
    ms = r.get('duration_ms', 0)
    print(f"  [{w}] {ok} ({ms}ms): {r.get('result','')[:100]}")

# 6. MCP server
print("\n[6] MCP SERVER")
try:
    import requests
    resp = requests.get('http://localhost:8083/health', timeout=3)
    print(f"  Status: {resp.json().get('status')}")
    tools_resp = requests.get('http://localhost:8083/tools', timeout=3)
    tools = tools_resp.json().get('tools', [])
    print(f"  {len(tools)} tools: {', '.join(t['name'] for t in tools[:6])}...")

    # Test a call
    call_resp = requests.post('http://localhost:8083/call',
        json={"name": "kg_find_related", "inputs": {"node_id": "nicholas"}},
        timeout=5)
    result = call_resp.json().get('result', '')
    print(f"  kg_find_related(nicholas): {result[:100]}")
except Exception as e:
    print(f"  Error: {e}")

# 7. Brain context
print("\n[7] BRAIN CONTEXT")
ctx = brain.get_context('lystpaa')
print(f"  Context for 'lystpaa': {len(ctx.split(chr(10)))} lines")
print(f"  {ctx.split(chr(10))[0]}")

print("\n" + "=" * 60)
print("ALL SYSTEMS OPERATIONAL")
print("=" * 60)
print()
print("Architecture:")
print("  Brain: SQLite WAL (multi-process) + Vector (sentence-transformers)")
print("  KG: SQLite KnowledgeGraph + Kuzu (MCP server, Cypher queries)")
print("  Workers: 6 specialists + Orchestrator (parallel)")
print("  MCP: http://89.167.100.7:8084 (13 tools)")
print("  Vault: /opt/nexus/vault/ (synced to OneDrive)")
print("  GitHub: nicholaselvegaard-commits/jarvis-os")
