with open('/opt/nexus/memory/brain.py', 'r') as f:
    content = f.read()

old_kg = '''    @property
    def kg(self):
        if self._kg is None:
            try:
                from memory.knowledge_graph import KnowledgeGraph
                self._kg = KnowledgeGraph()
            except Exception as e:
                logger.warning(f"KnowledgeGraph unavailable: {e}")
        return self._kg'''

new_kg = '''    @property
    def kg(self):
        if self._kg is None:
            # Try Kuzu first (faster, Cypher support), fallback to SQLite
            try:
                from memory.kuzu_graph import KuzuGraph
                self._kg = KuzuGraph()
            except Exception:
                try:
                    from memory.knowledge_graph import KnowledgeGraph
                    self._kg = KnowledgeGraph()
                except Exception as e2:
                    logger.warning("KnowledgeGraph unavailable: " + str(e2))
        return self._kg'''

content = content.replace(old_kg, new_kg)

with open('/opt/nexus/memory/brain.py', 'w') as f:
    f.write(content)

import py_compile
py_compile.compile('/opt/nexus/memory/brain.py', doraise=True)
print('brain.py: Kuzu as primary KG, syntax OK')
