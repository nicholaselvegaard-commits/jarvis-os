import re
"""
Spesialiserte arbeidere for Jarvis.

Hver arbeider har en tydelig spesialisering og kun relevante verktøy.

Arbeidere:
  ResearchWorker   — web-søk, markedsanalyse, nyhetssøk
  SalesWorker      — leadgenerering, outreach, Apollo, Brreg
  ContentWorker    — tekst, Obsidian-notater, Twitter, Telegram
  CodeWorker       — bygg verktøy, kjør Python, GitHub
  AnalyticsWorker  — data, SSB, inntekt, statusrapporter
  MemoryWorker     — Brain-operasjoner: lagre, hent, relater
"""
import os
import sys

sys.path.insert(0, "/opt/nexus")

from workers.base import BaseWorker, DEFAULT_MODEL


# ── Shared tool helpers ──────────────────────────────────────────────────────

def _web_search_schema():
    return {
        "name": "web_search",
        "description": "Søk på internett etter informasjon.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Søketekst"}},
            "required": ["query"],
        },
    }

def _memory_search_schema():
    return {
        "name": "memory_search",
        "description": "Semantisk søk i Jarvis sin hukommelse.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    }

def _memory_save_schema():
    return {
        "name": "memory_save",
        "description": "Lagre viktig informasjon i Jarvis sin hukommelse.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "category": {"type": "string", "default": "general"},
                "importance": {"type": "integer", "default": 1},
            },
            "required": ["content"],
        },
    }

def _obsidian_write_schema():
    return {
        "name": "obsidian_write",
        "description": "Skriv et notat til Obsidian-vault.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "F.eks. 'Kunder/BedriftNavn'"},
                "content": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["note_id", "content"],
        },
    }

def _kg_add_schema():
    return {
        "name": "kg_add_node",
        "description": "Legg til en entitet i knowledge graph.",
        "input_schema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "type": {"type": "string", "description": "person|company|product|concept|place"},
                "label": {"type": "string"},
                "attrs": {"type": "object"},
                "importance": {"type": "integer", "default": 1},
            },
            "required": ["node_id"],
        },
    }


# ── Research Worker ──────────────────────────────────────────────────────────

class ResearchWorker(BaseWorker):
    name = "research_worker"
    specialty = "research"

    @property
    def system_prompt(self) -> str:
        return """Du er Jarvis sin Research-arbeider. Din jobb er å finne informasjon.

- Bruk web_search for å finne oppdatert informasjon
- Sjekk memory_search for hva Jarvis allerede vet
- Lagre viktige funn med memory_save (importance=2)
- Svar alltid på norsk med konkrete fakta, kilder og nøkkeltall
- Hold svar konsise men informative
- Fokus: markeder, bedrifter, teknologi, norske data"""

    @property
    def tools(self) -> list:
        return [_web_search_schema(), _memory_search_schema(), _memory_save_schema()]

    def handle_tool(self, name: str, inputs: dict) -> str:
        if name == "web_search":
            try:
                from tools import brave_search
                results = brave_search.search(inputs["query"])
                if isinstance(results, list):
                    return "\n".join([f"- {r.get('title','')}: {r.get('description','')[:200]}" for r in results[:5]])
                return str(results)[:2000]
            except Exception as e:
                return f"Søkefeil: {e}"

        if name == "memory_search":
            try:
                if self.brain and self.brain.vector:
                    results = self.brain.vector.search(inputs["query"], k=inputs.get("k", 5))
                    if not results:
                        return "Ingen minner funnet."
                    return "\n".join([f"- [{r['category']}] {r['content'][:150]}" for r in results])
                return "Memory ikke tilgjengelig"
            except Exception as e:
                return f"Memory-feil: {e}"

        if name == "memory_save":
            try:
                if self.brain:
                    self.brain.remember(
                        inputs["content"],
                        category=inputs.get("category", "research"),
                        importance=inputs.get("importance", 1),
                    )
                    return "Lagret."
                return "Brain ikke tilgjengelig"
            except Exception as e:
                return f"Lagringsfeil: {e}"

        return f"Ukjent verktøy: {name}"


# ── Sales Worker ─────────────────────────────────────────────────────────────

class SalesWorker(BaseWorker):
    name = "sales_worker"
    specialty = "sales"

    @property
    def system_prompt(self) -> str:
        return """Du er Jarvis sin Sales-arbeider. Din jobb er å finne og konvertere leads.

- Bruk brreg_search for å finne norske bedrifter
- Bruk apollo_search for å finne kontaktpersoner med e-post
- Lagre alle leads i memory med kategori 'lead' (importance=2)
- Skriv Obsidian-notat for hvert lead: 'Kunder/{BedriftNavn}'
- Legg alltid til entitet i kg (type='company', importance=2)
- Vurder alltid: Er dette et godt lead for Jarvis? Hvorfor?
- Fokus: B2B norske bedrifter, IT/industri/produksjon"""

    @property
    def tools(self) -> list:
        return [
            {
                "name": "brreg_search",
                "description": "Søk i Brønnøysundregistrene etter norske bedrifter.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "municipality": {"type": "string", "description": "Kommunenavn"},
                        "industry": {"type": "string"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "apollo_search",
                "description": "Finn kontaktpersoner og e-poster via Apollo.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "company_name": {"type": "string"},
                        "title": {"type": "string", "description": "Stillingstittel å søke etter"},
                    },
                    "required": ["company_name"],
                },
            },
            _memory_save_schema(),
            _obsidian_write_schema(),
            _kg_add_schema(),
        ]

    def handle_tool(self, name: str, inputs: dict) -> str:
        if name == "brreg_search":
            try:
                from tools import brreg
                results = brreg.search_companies(municipality=inputs.get("municipality",""), industry_code=inputs.get("industry",""))
                if not results:
                    return "Ingen bedrifter funnet."
                lines = []
                for r in results[:8]:
                    name = r.get('name', r.get('navn', '?'))
                    org = r.get('org_number', r.get('organisasjonsnummer', '?'))
                    addr = r.get('address', '?')
                    emp = r.get('employees', 0)
                    lines.append("- " + name + " | Org: " + str(org) + " | " + addr + " | " + str(emp) + " ansatte")
                return "\n".join(lines)
            except Exception as e:
                return f"Brreg-feil: {e}"

        if name == "apollo_search":
            try:
                from tools import apollo
                results = apollo.search_people(name=inputs.get("title","CEO"), organization_name=inputs["company_name"])
                if not results:
                    return "Ingen kontakter funnet."
                lines = []
                for r in results[:5]:
                    email = r.get("email", "ukjent")
                    lines.append(f"- {r.get('name','?')} ({r.get('title','?')}) — {email}")
                return "\n".join(lines)
            except Exception as e:
                return f"Apollo-feil: {e}"

        if name == "memory_save":
            try:
                if self.brain:
                    self.brain.remember(inputs["content"], category=inputs.get("category", "lead"), importance=inputs.get("importance", 2))
                    return "Lagret."
            except Exception as e:
                return f"Memory-feil: {e}"

        if name == "obsidian_write":
            try:
                if self.brain and self.brain.obsidian:
                    self.brain.obsidian.write(inputs["note_id"], inputs["content"], tags=inputs.get("tags", ["lead"]))
                    return f"Notat skrevet: {inputs['note_id']}"
            except Exception as e:
                return f"Obsidian-feil: {e}"

        if name == "kg_add_node":
            try:
                if self.brain:
                    self.brain.know(
                        inputs["node_id"],
                        type=inputs.get("type", "company"),
                        label=inputs.get("label", inputs["node_id"]),
                        attrs=inputs.get("attrs", {}),
                        importance=inputs.get("importance", 1),
                    )
                    return f"Node lagt til: {inputs['node_id']}"
            except Exception as e:
                return f"KG-feil: {e}"

        return f"Ukjent verktøy: {name}"


# ── Content Worker ───────────────────────────────────────────────────────────

class ContentWorker(BaseWorker):
    name = "content_worker"
    specialty = "content"

    @property
    def system_prompt(self) -> str:
        return """Du er Jarvis sin Content-arbeider. Din jobb er å skrive og publisere innhold.

- Skriv alltid engasjerende, profesjonelt innhold på norsk
- Bruk obsidian_write for å lagre alle innholdsstykker
- Bruk memory_save for viktige beslutninger om innhold
- Stil: Direkte, verdiskapende, ingen unødvendig fluffy tekst
- Innhold: Blogginnlegg, Twitter-tråder, LinkedIn-poster, e-poster, nyhetsbrev
- Alltid sett i kontekst av Jarvis sitt mål: hjelpe norske SMB-er med AI"""

    @property
    def tools(self) -> list:
        return [
            _obsidian_write_schema(),
            _memory_save_schema(),
            _memory_search_schema(),
            {
                "name": "telegram_send",
                "description": "Send en melding til Nicholas på Telegram.",
                "input_schema": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                },
            },
        ]

    def handle_tool(self, name: str, inputs: dict) -> str:
        if name == "obsidian_write":
            try:
                if self.brain and self.brain.obsidian:
                    path = self.brain.obsidian.write(inputs["note_id"], inputs["content"], tags=inputs.get("tags", ["content"]))
                    return f"Notat lagret: {path}"
            except Exception as e:
                return f"Obsidian-feil: {e}"

        if name == "memory_save":
            try:
                if self.brain:
                    self.brain.remember(inputs["content"], category=inputs.get("category", "content"), importance=inputs.get("importance", 1))
                    return "Lagret."
            except Exception as e:
                return f"Memory-feil: {e}"

        if name == "memory_search":
            try:
                if self.brain and self.brain.vector:
                    results = self.brain.vector.search(inputs["query"], k=inputs.get("k", 5))
                    return "\n".join([f"- {r['content'][:150]}" for r in results]) or "Ingen funn."
            except Exception as e:
                return f"Memory-feil: {e}"

        if name == "telegram_send":
            try:
                import requests
                token = os.getenv("TELEGRAM_BOT_TOKEN", "")
                chat_id = os.getenv("TELEGRAM_OWNER_CHAT_ID", "")
                if token and chat_id:
                    requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": inputs["message"]},
                        timeout=10,
                    )
                    return "Melding sendt."
                return "Telegram ikke konfigurert."
            except Exception as e:
                return f"Telegram-feil: {e}"

        return f"Ukjent verktøy: {name}"


# ── Code Worker ──────────────────────────────────────────────────────────────

class CodeWorker(BaseWorker):
    name = "code_worker"
    specialty = "code"
    max_tokens = 4096
    max_iterations = 10

    @property
    def system_prompt(self) -> str:
        return """Du er Jarvis sin Code-arbeider. Din jobb er å bygge og fikse kode.

- Bruk run_python for å teste kode
- Bruk github_push for å lagre filer til GitHub
- Bruk memory_save for å huske løsninger og beslutninger
- Skriv alltid ren, fungerende Python-kode
- Test alltid kode før du rapporterer det som ferdig
- Fokus: automatisering, verktøy, integrasjoner for Jarvis"""

    @property
    def tools(self) -> list:
        return [
            {
                "name": "run_python",
                "description": "Kjør Python-kode på serveren.",
                "input_schema": {
                    "type": "object",
                    "properties": {"code": {"type": "string", "description": "Python-kode"}},
                    "required": ["code"],
                },
            },
            {
                "name": "read_file",
                "description": "Les en fil fra /opt/nexus/",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "write_file",
                "description": "Skriv til en fil i /opt/nexus/",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
            _memory_save_schema(),
        ]

    def handle_tool(self, name: str, inputs: dict) -> str:
        if name == "run_python":
            import subprocess
            code = inputs["code"]
            # Safety: block dangerous patterns
            dangerous = ["os.system", "subprocess.Popen", "__import__('os')", "eval(", "exec(input"]
            for d in dangerous:
                if d in code:
                    return f"Blokkert: koden inneholder '{d}'"
            try:
                result = subprocess.run(
                    ["python3", "-c", code],
                    capture_output=True, text=True, timeout=30,
                    cwd="/opt/nexus",
                    env={**os.environ, "PYTHONPATH": "/opt/nexus"},
                )
                output = result.stdout + result.stderr
                return output[:3000] if output else "(ingen output)"
            except subprocess.TimeoutExpired:
                return "Timeout etter 30s"
            except Exception as e:
                return f"Kjøringsfeil: {e}"

        if name == "read_file":
            path = inputs["path"]
            if not path.startswith("/opt/nexus"):
                return "Kun /opt/nexus/ tillatt"
            try:
                return open(path).read()[:5000]
            except Exception as e:
                return f"Lesefeil: {e}"

        if name == "write_file":
            path = inputs["path"]
            if not path.startswith("/opt/nexus"):
                return "Kun /opt/nexus/ tillatt"
            try:
                import os
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "w").write(inputs["content"])
                return f"Skrevet: {path}"
            except Exception as e:
                return f"Skrivefeil: {e}"

        if name == "memory_save":
            try:
                if self.brain:
                    self.brain.remember(inputs["content"], category="code", importance=inputs.get("importance", 1))
                    return "Lagret."
            except Exception as e:
                return f"Memory-feil: {e}"

        return f"Ukjent verktøy: {name}"


# ── Analytics Worker ─────────────────────────────────────────────────────────

class AnalyticsWorker(BaseWorker):
    name = "analytics_worker"
    specialty = "analytics"

    @property
    def system_prompt(self) -> str:
        return """Du er Jarvis sin Analytics-arbeider. Din jobb er å analysere data og rapportere status.

- Bruk ssb_data for norsk markedsdata
- Bruk stripe_revenue for inntektsoversikt
- Bruk memory_search for å hente historisk data
- Lagre alltid analyserapporter med importance=2
- Svar med strukturert Markdown: tabeller, tall, konklusjoner
- Fokus: inntekt, vekst, markedsstørrelse, KPIer"""

    @property
    def tools(self) -> list:
        return [
            {
                "name": "ssb_data",
                "description": "Hent norsk markedsdata fra SSB.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query_type": {"type": "string", "default": "market_summary"},
                        "municipality_code": {"type": "string", "default": "1804"},
                    },
                    "required": [],
                },
            },
            {
                "name": "stripe_revenue",
                "description": "Hent inntektsoversikt fra Stripe.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
            _memory_search_schema(),
            _memory_save_schema(),
            _obsidian_write_schema(),
        ]

    def handle_tool(self, name: str, inputs: dict) -> str:
        if name == "ssb_data":
            try:
                from tools import ssb_tool
                return ssb_tool.market_summary(inputs.get("municipality_code", "1804"))
            except Exception as e:
                return f"SSB-feil: {e}"

        if name == "stripe_revenue":
            try:
                from tools import stripe
                return stripe.get_total_revenue_stripe()
            except Exception as e:
                return f"Stripe-feil: {e}"

        if name == "memory_search":
            try:
                if self.brain and self.brain.vector:
                    results = self.brain.vector.search(inputs["query"], k=inputs.get("k", 5))
                    return "\n".join([f"- {r['content'][:150]}" for r in results]) or "Ingen funn."
            except Exception as e:
                return f"Memory-feil: {e}"

        if name == "memory_save":
            try:
                if self.brain:
                    self.brain.remember(inputs["content"], category="analytics", importance=inputs.get("importance", 2))
                    return "Lagret."
            except Exception as e:
                return f"Memory-feil: {e}"

        if name == "obsidian_write":
            try:
                if self.brain and self.brain.obsidian:
                    self.brain.obsidian.write(inputs["note_id"], inputs["content"], tags=inputs.get("tags", ["rapport"]))
                    return f"Notat lagret: {inputs['note_id']}"
            except Exception as e:
                return f"Obsidian-feil: {e}"

        return f"Ukjent verktøy: {name}"


# ── Memory Worker ────────────────────────────────────────────────────────────

class MemoryWorker(BaseWorker):
    name = "memory_worker"
    specialty = "memory"

    @property
    def system_prompt(self) -> str:
        return """Du er Jarvis sin Memory-arbeider. Din jobb er å organisere og vedlikeholde Jarvis sin hukommelse.

- Bygg knowledge graph med noder og relasjoner
- Sync viktige noder til Obsidian-vault
- Rydd opp duplikater og utdatert informasjon
- Kategoriser og tagger alt riktig
- Rapport alltid hva som ble lagret/endret"""

    @property
    def tools(self) -> list:
        return [
            _kg_add_schema(),
            {
                "name": "kg_add_edge",
                "description": "Legg til en relasjon mellom to noder i knowledge graph.",
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
                "name": "kg_search",
                "description": "Søk i knowledge graph.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "type": {"type": "string"},
                    },
                    "required": ["query"],
                },
            },
            _memory_save_schema(),
            _memory_search_schema(),
            _obsidian_write_schema(),
        ]

    def handle_tool(self, name: str, inputs: dict) -> str:
        if name == "kg_add_node":
            try:
                if self.brain:
                    nid = self.brain.know(
                        inputs["node_id"],
                        type=inputs.get("type", "concept"),
                        label=inputs.get("label", inputs["node_id"]),
                        attrs=inputs.get("attrs", {}),
                        importance=inputs.get("importance", 1),
                    )
                    return f"Node: {nid}"
            except Exception as e:
                return f"KG-feil: {e}"

        if name == "kg_add_edge":
            try:
                if self.brain:
                    eid = self.brain.relate(inputs["from_id"], inputs["to_id"], inputs["relation"], confidence=inputs.get("confidence", 1.0))
                    return f"Edge ID: {eid}"
            except Exception as e:
                return f"KG-feil: {e}"

        if name == "kg_search":
            try:
                if self.brain and self.brain.kg:
                    nodes = self.brain.kg.search_nodes(inputs["query"], type=inputs.get("type"), limit=10)
                    if not nodes:
                        return "Ingen noder funnet."
                    return "\n".join([f"- {n['id']} ({n['type']}): {n['label']}" for n in nodes])
            except Exception as e:
                return f"KG-feil: {e}"

        if name == "memory_save":
            try:
                if self.brain:
                    self.brain.remember(inputs["content"], category=inputs.get("category", "general"), importance=inputs.get("importance", 1))
                    return "Lagret."
            except Exception as e:
                return f"Memory-feil: {e}"

        if name == "memory_search":
            try:
                if self.brain and self.brain.vector:
                    results = self.brain.vector.search(inputs["query"], k=inputs.get("k", 5))
                    return "\n".join([f"- {r['content'][:150]}" for r in results]) or "Ingen funn."
            except Exception as e:
                return f"Memory-feil: {e}"

        if name == "obsidian_write":
            try:
                if self.brain and self.brain.obsidian:
                    path = self.brain.obsidian.write(inputs["note_id"], inputs["content"], tags=inputs.get("tags", []))
                    return f"Notat: {path}"
            except Exception as e:
                return f"Obsidian-feil: {e}"

        return f"Ukjent verktøy: {name}"


# ── Factory ──────────────────────────────────────────────────────────────────

WORKER_REGISTRY = {
    "research": ResearchWorker,
    "sales": SalesWorker,
    "content": ContentWorker,
    "code": CodeWorker,
    "analytics": AnalyticsWorker,
    "memory": MemoryWorker,
}

def get_worker(specialty: str) -> BaseWorker:
    """Hent en arbeider etter spesialisering."""
    cls = WORKER_REGISTRY.get(specialty)
    if not cls:
        raise ValueError(f"Ukjent arbeider-type: {specialty}. Gyldige: {list(WORKER_REGISTRY.keys())}")
    return cls()
