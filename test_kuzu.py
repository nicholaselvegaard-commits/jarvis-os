import sys
sys.path.insert(0, '/opt/nexus')

from memory.kuzu_graph import KuzuGraph
from memory.knowledge_graph import KnowledgeGraph

# Test Kuzu
kg = KuzuGraph()
kg.add_node('nicholas', type='person', label='Nicholas', attrs={'role': 'eier'}, importance=3)
kg.add_node('jarvis', type='tool', label='Jarvis', attrs={'role': 'CEO agent'}, importance=3)
kg.add_node('lystpaa', type='company', label='Lystpaa', attrs={'status': 'potensiell kunde', 'sted': 'Bodo'}, importance=2)
kg.add_node('aidn', type='company', label='AIDN AS', attrs={'ansatte': 127, 'sted': 'Bodo', 'naeringskode': '62.100'}, importance=2)
kg.add_node('aioffice', type='product', label='AI Office', attrs={'status': 'under_bygging'}, importance=2)

kg.add_edge('nicholas', 'jarvis', 'eier')
kg.add_edge('nicholas', 'lystpaa', 'er_kontakt_for')
kg.add_edge('lystpaa', 'jarvis', 'er_potensiell_kunde_av')
kg.add_edge('aidn', 'jarvis', 'er_potensiell_kunde_av')
kg.add_edge('nicholas', 'aioffice', 'bygger')
kg.add_edge('jarvis', 'aioffice', 'driver')

print('=== KUZU SUMMARY ===')
print(kg.summary())
print()

print('=== RELATED TO NICHOLAS ===')
for r in kg.find_related('nicholas'):
    print(f"  {r['direction']} {r['node']['label']} via {r['relation']}")
print()

print('=== CYPHER: Alle companies ===')
rows = kg.cypher("MATCH (n:Node) WHERE n.type = 'company' RETURN n.node_id, n.label, n.importance ORDER BY n.importance DESC")
for r in rows:
    print(' ', r)
print()

print('=== SEARCH: "kunde" ===')
results = kg.search_nodes('kunde')
for r in results:
    print(f"  {r['id']} ({r['type']}): {r['label']}")
print()

# Migrate SQLite -> Kuzu
print('=== MIGRATE FROM SQLITE KG ===')
sqlite_kg = KnowledgeGraph()
stats = kg.migrate_from_sqlite(sqlite_kg)
print('Migrated:', stats)
print()
print('=== FINAL SUMMARY ===')
print(kg.summary())
