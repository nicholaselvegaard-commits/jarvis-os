"""Fix KuzuGraph to open/close connection per operation to allow multi-process access."""
with open('/opt/nexus/memory/kuzu_graph.py', 'r') as f:
    content = f.read()

# Replace the persistent connection with per-operation open/close
old_init = '''    def __init__(self, db_path=None):
        import kuzu
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)  # only create parent
        self._db = kuzu.Database(str(self.db_path))
        self._conn = kuzu.Connection(self._db)
        self._init_schema()'''

new_init = '''    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self):
        """Get a fresh connection. Kuzu allows one writer at a time."""
        import kuzu
        db = kuzu.Database(str(self.db_path))
        return kuzu.Connection(db)'''

content = content.replace(old_init, new_init)

# Replace all self._conn.execute calls with self._get_conn().execute
content = content.replace('self._conn.execute(', 'self._get_conn().execute(')

# Fix _init_schema to use get_conn
old_schema = '''    def _init_schema(self):
        """Create node and relationship tables if they don't exist."""
        try:
            self._conn.execute("""'''

new_schema = '''    def _init_schema(self):
        """Create node and relationship tables if they don't exist."""
        try:
            conn = self._get_conn()
            conn.execute("""'''

content = content.replace(old_schema, new_schema)

# Also fix the subsequent schema call
content = content.replace(
    '''        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.warning(f"Node table: {e}")

        try:
            self._conn.execute("""''',
    '''        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.warning(f"Node table: {e}")

        try:
            conn = self._get_conn()
            conn.execute("""'''
)

with open('/opt/nexus/memory/kuzu_graph.py', 'w') as f:
    f.write(content)

import py_compile
py_compile.compile('/opt/nexus/memory/kuzu_graph.py', doraise=True)
print('kuzu_graph.py: per-operation connections, syntax OK')
