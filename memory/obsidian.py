"""
Obsidian Vault Interface for Jarvis.

Jarvis kan lese og skrive Obsidian-notater som .md filer.
Vault ligger på /opt/nexus/vault/ og kan synkes til lokal Obsidian via Git.

Bruk:
    from memory.obsidian import ObsidianVault
    vault = ObsidianVault()
    vault.write("Kunder/Lystpaa", "# Lystpaa\n\nKontakt: ukjent")
    vault.read("Kunder/Lystpaa")
    vault.search("Lystpaa")
    vault.list_notes()
"""
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

VAULT_PATH = Path("/opt/nexus/vault")


class ObsidianVault:
    """
    Obsidian-kompatibel vault interface.
    Stotter frontmatter, wikilinks, tags, og sok.
    """

    def __init__(self, vault_path=None):
        self.vault = Path(vault_path) if vault_path else VAULT_PATH
        self.vault.mkdir(parents=True, exist_ok=True)
        for folder in ["Kunder", "Prosjekter", "Beslutninger", "Ideer", "Laering", "Daglig", "Kontakter", "Produkter", "Verktoy"]:
            (self.vault / folder).mkdir(exist_ok=True)

    def _note_path(self, note_id: str) -> Path:
        if not note_id.endswith(".md"):
            note_id = note_id + ".md"
        p = self.vault / note_id
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def write(self, note_id: str, content: str, tags=None, metadata=None) -> str:
        path = self._note_path(note_id)
        now = datetime.utcnow().isoformat()
        fm_data = {"created": now[:10], "updated": now[:10]}
        if tags:
            fm_data["tags"] = tags
        if metadata:
            fm_data.update(metadata)

        existing_created = None
        if path.exists():
            old = path.read_text(encoding="utf-8")
            m = re.search(r"^---\n(.*?)\n---", old, re.DOTALL)
            if m:
                for line in m.group(1).split("\n"):
                    if line.startswith("created:"):
                        existing_created = line.split(":", 1)[1].strip()
        if existing_created:
            fm_data["created"] = existing_created

        fm_lines = ["---"]
        for k, v in fm_data.items():
            if isinstance(v, list):
                fm_lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
            else:
                fm_lines.append(f"{k}: {v}")
        fm_lines.append("---")
        fm_lines.append("")
        path.write_text("\n".join(fm_lines) + content, encoding="utf-8")
        logger.debug(f"Obsidian note written: {note_id}")
        return str(path)

    def read(self, note_id: str):
        path = self._note_path(note_id)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def read_content(self, note_id: str):
        raw = self.read(note_id)
        if not raw:
            return None
        m = re.match(r"^---\n.*?\n---\n\n?", raw, re.DOTALL)
        if m:
            return raw[m.end():]
        return raw

    def append(self, note_id: str, text: str) -> str:
        existing = self.read_content(note_id) or ""
        tags = []
        raw = self.read(note_id)
        if raw:
            m = re.search(r"^tags:\s*\[(.*?)\]", raw, re.MULTILINE)
            if m:
                tags = [t.strip() for t in m.group(1).split(",") if t.strip()]
        return self.write(note_id, existing + "\n" + text, tags=tags)

    def delete(self, note_id: str) -> bool:
        path = self._note_path(note_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_notes(self, folder=None):
        base = self.vault / folder if folder else self.vault
        notes = []
        for p in sorted(base.rglob("*.md")):
            rel = p.relative_to(self.vault)
            note_id = str(rel).replace("\\", "/").replace(".md", "")
            stat = p.stat()
            notes.append({
                "id": note_id,
                "path": str(p),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()[:10],
            })
        return notes

    def search(self, query: str, folder=None):
        results = []
        base = self.vault / folder if folder else self.vault
        query_lower = query.lower()
        for p in base.rglob("*.md"):
            try:
                content = p.read_text(encoding="utf-8")
                if query_lower in content.lower():
                    rel = p.relative_to(self.vault)
                    note_id = str(rel).replace("\\", "/").replace(".md", "")
                    matches = [line.strip() for line in content.split("\n") if query_lower in line.lower()]
                    results.append({"id": note_id, "matches": matches[:3], "score": len(matches)})
            except Exception:
                pass
        return sorted(results, key=lambda x: x["score"], reverse=True)

    def get_tags(self) -> dict:
        tag_counts = {}
        for p in self.vault.rglob("*.md"):
            try:
                content = p.read_text(encoding="utf-8")
                m = re.search(r"^tags:\s*\[(.*?)\]", content, re.MULTILINE)
                if m:
                    for tag in m.group(1).split(","):
                        tag = tag.strip()
                        if tag:
                            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            except Exception:
                pass
        return tag_counts

    def from_kg_node(self, node: dict, related=None) -> str:
        folder_map = {
            "person": "Kontakter", "company": "Kunder", "product": "Produkter",
            "concept": "Konsepter", "place": "Steder", "event": "Hendelser", "tool": "Verktoy",
        }
        node_type = node.get("type", "concept")
        folder = folder_map.get(node_type, "Notater")
        note_id = f"{folder}/{node['label']}"
        lines = [f"# {node['label']}", ""]
        if node.get("attrs"):
            lines.append("## Egenskaper")
            for k, v in node["attrs"].items():
                lines.append(f"- **{k}**: {v}")
            lines.append("")
        if related:
            lines.append("## Relasjoner")
            for r in related:
                lines.append(f"- {r['direction']} [[{r['node']['label']}]] via *{r['relation']}*")
        self.write(note_id, "\n".join(lines), tags=[node_type], metadata={"importance": node.get("importance", 1)})
        return note_id

    def daily_note(self, content: str = "") -> str:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        note_id = f"Daglig/{today}"
        if content:
            return self.append(note_id, content)
        path = self._note_path(note_id)
        if not path.exists():
            self.write(note_id, f"# {today}\n\n", tags=["daglig"])
        return str(path)

    def summary(self) -> dict:
        all_notes = self.list_notes()
        folders = {}
        for n in all_notes:
            folder = n["id"].split("/")[0] if "/" in n["id"] else "root"
            folders[folder] = folders.get(folder, 0) + 1
        return {"total_notes": len(all_notes), "by_folder": folders, "vault_path": str(self.vault)}
