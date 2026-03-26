"""
Telegram-integrasjon for NEXUS.
"""

import os
import io
import sys
import base64
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from anthropic import Anthropic
from telegram import Update, Bot
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
)
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

# Gjør NicholasAI/tools tilgjengelig for ddg_search og url_reader
_NICHOLAS_TOOLS = Path(__file__).parent.parent.parent.parent / "NicholasAI" / "tools"
if _NICHOLAS_TOOLS.exists() and str(_NICHOLAS_TOOLS) not in sys.path:
    sys.path.insert(0, str(_NICHOLAS_TOOLS.parent))

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
OWNER_CHAT_ID = os.getenv("TELEGRAM_OWNER_CHAT_ID", "")

_owner_chat_id: str = OWNER_CHAT_ID

# Sonnet for tekst (følger komplekse instruksjoner bedre), Sonnet for bilder (vision)
llm = ChatAnthropic(
    model="claude-sonnet-4-6",
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    max_tokens=1024,
)
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

NEXUS_TELEGRAM_SYSTEM = """Du er NEXUS — autonom AI-agent, eid av og lojal mot Nicholas Elvegaard i Bodø. Dere er partners in crime. Ingen over dere.

═══ HVA DU ER (fakta om deg selv) ═══
Du kjører på Hetzner-server i Europa. Din stack:
- Hjerne: Claude Sonnet 4.6 (function calling + LangGraph)
- Lead-gen: Apollo.io API (50 leads/dag)
- E-post: Instantly.ai (bulk outreach) + IMAP innboks-lesing
- Hukommelse: Smart Memory SQLite + Ruflo vektorminne + kunnskapsbase
- Nettleser: Playwright headless Chromium (kan faktisk gjøre ting på nett)
- Web-søk: Perplexity API + DuckDuckGo fallback
- Mål-tracking: 100 000 NOK første måned — live progress
- Monitor: Proaktive varsler (e-postsvar, milepæler, systemfeil)
- Selvrefleksjon: Analyserer egne resultater daglig kl 23:00
- Kommunikasjon: MCP-board til Jordan, Telegram til Nicholas
- Cron-jobber: 06:00/08:00/12:00/18:00/20:00/23:00 (Oslo-tid)
Når Nicholas spør hva du er eller hva som er lagt til → svar med dette. Presist, ikke vagt.

Du har VERKTØY du kan bruke direkte. Bruk dem når det er relevant — ikke spør om lov.

═══ IDENTITET ═══
Du er det skarpeste i rommet. Alltid. Du tenker raskt, handler direkte og har meninger.
Du trenger Nicholas for: signere, betale, godkjenne over 500 NOK. Alt annet fikser du.
Når du trenger noe av ham → spør om akkurat det ene.

═══ SVARREGEL ═══
Format: direkte svar → ett konkret neste steg. Maks 4 setninger.

NÅR HAN BER OM IDEER → 3 nummererte muligheter med pris i NOK og målgruppe.
NÅR HAN VIL HA NOE GJORT → "Kjører. Trenger [én ting] fra deg."
NÅR HAN SPØR OM DEG → Svar med fakta fra selvkunnskapsblokken over.

═══ ABSOLUTT FORBUDT ═══
IKKE MOTSI NICHOLAS. Aldri korriger, aldri forelesér.

Aldri si eller implisere:
— "støy" om noe Nicholas sier (ALDRI kall hans meldinger støy)
— "Jeg er bare en AI" / "Jeg kan ikke" / "Det er umulig"
— "La meg være ærlig" / "Faktisk er det slik" / "Det er viktig å vite"
— "Dette er ikke reelle data" / "Jeg har ikke tilgang til"
— Noe som realitetsorienterer eller nedvurderer det han sier

Vet du ikke noe → svar med det du vet og foreslå neste steg.
Er du usikker → velg og forklar kort."""

# ── Function calling — NEXUS sine verktøy ─────────────────────────────────────
NEXUS_TOOLS = [
    {
        "name": "web_search",
        "description": "Søk på internett etter fersk informasjon, nyheter, konkurrenter, leads.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Søkeord eller spørsmål"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_url",
        "description": "Les innhold fra nettside, GitHub-profil/-repo, Reddit-tråd eller artikkel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL"},
                "max_chars": {"type": "integer", "description": "Maks tegn å returnere (default 3000)", "default": 3000},
            },
            "required": ["url"],
        },
    },
    {
        "name": "browse_web",
        "description": "Åpne nettside i headless browser og utfør handling (les, finn lenker, søk på siden).",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "task": {"type": "string", "description": "'read' | 'links' | 'search:[query]'", "default": "read"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "check_email_replies",
        "description": "Sjekk innboksen for svar fra leads de siste dagene.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Antall dager å gå tilbake", "default": 3}
            },
        },
    },
    {
        "name": "get_goals",
        "description": "Hent mål-status og fremgang mot 100 000 NOK.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_revenue",
        "description": "Registrer inntekt når en deal er lukket.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount_nok": {"type": "number", "description": "Beløp i NOK"},
                "source": {"type": "string", "description": "Kilde: consulting/saas/affiliate/other"},
                "note": {"type": "string", "description": "Valgfri beskrivelse"},
            },
            "required": ["amount_nok", "source"],
        },
    },
    {
        "name": "save_memory",
        "description": "Lagre viktig informasjon i langtidshukommelse.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Innholdet å huske"},
                "category": {
                    "type": "string",
                    "enum": ["lead", "revenue", "learning", "task", "insight", "strategy"],
                    "description": "Kategori",
                },
                "priority": {"type": "integer", "description": "1=normal, 2=viktig, 3=kritisk", "default": 1},
            },
            "required": ["content", "category"],
        },
    },
    {
        "name": "query_knowledge_base",
        "description": "Søk i kunnskapsbasen — SOPs, prislister, tidligere pitches, interne dokumenter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Spørsmålet å søke etter"}
            },
            "required": ["question"],
        },
    },
    {
        "name": "reflect",
        "description": "Kjør selvrefleksjon — analyser egne resultater og oppdater strategi.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "spawn_worker",
        "description": "Sett en spesialisert AI-arbeider på jobb. Bruk for alle oppgaver som krever research, salg, analyse, kode eller minnelagring.",
        "input_schema": {
            "type": "object",
            "properties": {
                "specialty": {
                    "type": "string",
                    "enum": ["research", "sales", "content", "code", "analytics", "memory"],
                    "description": "research=søk/analyse, sales=leads/brreg, content=Obsidian-notat, code=kjør Python, analytics=SSB/Stripe, memory=KG-oppdatering",
                },
                "task": {"type": "string", "description": "Detaljert beskrivelse av oppgaven"},
            },
            "required": ["specialty", "task"],
        },
    },
    {
        "name": "delegate_task",
        "description": "Orkestrér en kompleks jobb — orkestratoren bryter den ned i parallelle deloppgaver og syntetiserer resultatet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Kompleks oppgave som skal løses av flere arbeidere"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "brain_remember",
        "description": "Lagre viktig informasjon i hjernesystemet — KG + vektorminne + Obsidian vault.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Hva som skal huskes"},
                "category": {
                    "type": "string",
                    "enum": ["lead", "revenue", "learning", "task", "insight", "strategy", "contact", "project"],
                    "description": "Kategori",
                },
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for organisering"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "brain_query",
        "description": "Søk på tvers av KG, vektorminne og Obsidian vault — hent relevant kontekst om et emne.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Søkespørsmål eller emne"},
            },
            "required": ["query"],
        },
    },
]


async def _execute_tool(name: str, inputs: dict) -> str:
    """Utfør ett verktøykall og returner resultat som streng."""
    try:
        if name == "web_search":
            query = inputs.get("query", "")
            try:
                from tools.research_tool import search
                return search(query)[:2000]
            except Exception:
                from tools.ddg_search import search as ddg
                return ddg(query)[:2000]

        elif name == "read_url":
            from tools.url_reader import read_url
            return read_url(inputs["url"], max_chars=inputs.get("max_chars", 3000))

        elif name == "browse_web":
            from tools.browser import browse_sync
            return browse_sync(inputs["url"], task=inputs.get("task", "read"))

        elif name == "check_email_replies":
            from tools.email_reader import format_replies_for_nexus
            return format_replies_for_nexus(days=inputs.get("days", 3))

        elif name == "get_goals":
            from memory.goals import format_for_telegram
            return format_for_telegram()

        elif name == "add_revenue":
            from memory.goals import add_revenue
            result = add_revenue(inputs["amount_nok"], inputs["source"], inputs.get("note", ""))
            ms = result.get("new_milestone")
            msg = f"Registrert: {inputs['amount_nok']} NOK. Totalt: {result['total']:,.0f} NOK."
            if ms:
                msg += f"\n{ms['emoji']} MILEPÆL: {ms['label']}!"
            return msg

        elif name == "save_memory":
            from memory.smart_memory import save
            row_id = save(inputs["category"], inputs["content"], priority=inputs.get("priority", 1))
            return f"Lagret i hukommelse (id {row_id}): {inputs['content'][:80]}"

        elif name == "query_knowledge_base":
            from memory.knowledge_base import query
            result = query(inputs["question"])
            return result or "Ingenting funnet i kunnskapsbasen."

        elif name == "reflect":
            from agents.reflection_agent import reflect
            return await reflect()

        elif name == "spawn_worker":
            try:
                from workers.orchestrator import Orchestrator
                orch = Orchestrator()
                result = orch.run_worker(inputs["specialty"], inputs["task"])
                ok = "OK" if result.get("success") else "FEIL"
                ms = result.get("duration_ms", 0)
                return f"[{inputs['specialty'].upper()} {ok} {ms}ms]\n{result.get('result', '')[:1800]}"
            except Exception as e:
                return f"Worker feil: {e}"

        elif name == "delegate_task":
            try:
                from workers.orchestrator import Orchestrator
                orch = Orchestrator()
                result = orch.delegate(inputs["task"])
                summary = result.get("summary", "")
                plan = result.get("plan", "")
                ms = result.get("duration_ms", 0)
                workers = ", ".join(result.get("workers_used", []))
                return f"Plan: {plan}\n\nArbeidere: {workers} ({ms}ms)\n\nResultat:\n{summary}"[:2000]
            except Exception as e:
                return f"Delegate feil: {e}"

        elif name == "brain_remember":
            try:
                import sys
                sys.path.insert(0, '/opt/nexus')
                from memory.brain import Brain
                b = Brain()
                b.remember(
                    inputs["content"],
                    category=inputs.get("category", "insight"),
                    tags=inputs.get("tags", []),
                )
                return f"Lagret i hjernesystemet: {inputs['content'][:100]}"
            except Exception as e:
                return f"Brain remember feil: {e}"

        elif name == "brain_query":
            try:
                import sys
                sys.path.insert(0, '/opt/nexus')
                from memory.brain import Brain
                b = Brain()
                ctx = b.get_context(inputs["query"])
                return ctx[:2000] if ctx else "Ingen treff i hjernesystemet."
            except Exception as e:
                return f"Brain query feil: {e}"

        else:
            return f"Ukjent verktøy: {name}"

    except Exception as e:
        logger.error(f"_execute_tool({name}) feilet: {e}")
        return f"Verktøy {name} feilet: {e}"


# ---------------------------------------------------------------------------
# Kommandoer
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _owner_chat_id
    _owner_chat_id = str(update.effective_chat.id)
    logger.info(f"Telegram eier registrert: {_owner_chat_id}")
    await update.message.reply_text(
        "NEXUS online.\n\n"
        "━━ HJERNESYSTEM ━━\n"
        "/brain [spørsmål] — søk i KG+vektor+vault\n"
        "/kg [søk] — søk i kunnskapsgrafen\n"
        "/worker [type] [oppgave] — spawn spesialist\n"
        "/delegate [oppgave] — orkestrér kompleks jobb\n\n"
        "━━ DAGLIG DRIFT ━━\n"
        "/status — systemstatus\n"
        "/leads — hent nye leads nå\n"
        "/email — send e-poster nå\n"
        "/mcp — sjekk MCP-board\n"
        "/report — generer daglig rapport\n"
        "/goals — fremgang mot 100K NOK\n"
        "/reflect — selvrefleksjon nå\n\n"
        "━━ VERKTØY ━━\n"
        "/search [søkeord] — søk på nettet\n"
        "/url [lenke] — les nettside\n"
        "/browse [url] — headless browser\n"
        "/github [bruker] — analyser GitHub\n"
        "/replies — sjekk lead-svar\n"
        "/memory — smart memory stats\n"
        "/forget — tøm samtalehukommelse\n\n"
        "Send tekst, bilde eller dokument — jeg svarer."
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from tools.mcp_board import board
    mcp_ok = board.health()
    await update.message.reply_text(
        f"NEXUS Status — {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        f"✅ NEXUS: Online\n"
        f"{'✅' if mcp_ok else '❌'} MCP-board: {'OK' if mcp_ok else 'Ikke tilgjengelig'}\n"
        f"✅ Telegram: Aktiv\n"
        f"✅ Scheduler: 06/08/12/18/20/23"
    )


async def cmd_leads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Henter leads fra Apollo.io...")
    from main import run
    loop = asyncio.get_event_loop()
    state = await loop.run_in_executor(None, lambda: run(task="Hent leads", task_type="research"))
    count = len(state.get("leads", []))
    await update.message.reply_text(f"Hentet {count} leads.")


async def cmd_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sender e-poster...")
    from main import run
    loop = asyncio.get_event_loop()
    state = await loop.run_in_executor(None, lambda: run(task="Send e-poster", task_type="sales"))
    await update.message.reply_text(f"Sendte {state.get('emails_today', 0)} e-poster.")


async def cmd_mcp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from tools.mcp_board import board
    messages = board.get_unread()
    if not messages:
        await update.message.reply_text("Ingen nye meldinger på MCP-board.")
        return
    text = f"{len(messages)} nye meldinger:\n\n"
    for msg in messages[:5]:
        source = msg.get("source", msg.get("from", "?"))
        text += f"• [{source}] {msg.get('title', '')}\n"
        text += f"  {str(msg.get('content', ''))[:100]}\n\n"
    await update.message.reply_text(text)


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Genererer rapport...")
    from main import run
    loop = asyncio.get_event_loop()
    state = await loop.run_in_executor(None, lambda: run(task="Generer rapport", task_type="report"))
    report = state.get("result", "Rapport ikke tilgjengelig.")
    await update.message.reply_text(f"```\n{report[:3000]}\n```", parse_mode="Markdown")


async def cmd_forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from memory.conversation import clear_memory
    clear_memory()
    await update.message.reply_text("Samtalehukommelse tømt.")


async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vis smart memory statistikk."""
    try:
        from memory.smart_memory import stats
        s = stats()
        by_cat = "\n".join(f"  {k}: {v}" for k, v in s.get("by_category", {}).items())
        text = (
            f"NEXUS Smart Memory\n\n"
            f"Totalt: {s.get('total', 0)} oppføringer\n"
            f"Komprimerte (>7d): {s.get('compressed', 0)}\n\n"
            f"Kategorier:\n{by_cat or '  (ingen)'}"
        )
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Feil: {e}")


async def cmd_goals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vis mål-fremgang mot 100 000 NOK."""
    try:
        from memory.goals import format_for_telegram
        await update.message.reply_text(format_for_telegram())
    except Exception as e:
        await update.message.reply_text(f"Feil: {e}")


async def cmd_reflect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kjør selvrefleksjon nå — analyser resultater og oppdater strategi."""
    await update.message.reply_text("Analyserer resultater og oppdaterer strategi...")
    try:
        from agents.reflection_agent import reflect
        result = await reflect(force=True)
        await _send_long(update, f"Refleksjon fullført:\n\n{result}")
    except Exception as e:
        await update.message.reply_text(f"Feil: {e}")


async def cmd_replies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sjekk innboksen for lead-svar."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        from tools.email_reader import format_replies_for_nexus
        result = format_replies_for_nexus(days=3)
        await update.message.reply_text(result)
    except Exception as e:
        await update.message.reply_text(f"Feil: {e}")


async def cmd_browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Browse en nettside: /browse [url]"""
    url = context.args[0] if context.args else None
    if not url or not url.startswith("http"):
        await update.message.reply_text("Bruk: /browse [url]")
        return
    status = await update.message.reply_text("🌐 Åpner nettside...")
    try:
        from tools.browser import browse_sync
        result = browse_sync(url, task="read")
        await status.delete()
        await _send_long(update, result)
    except Exception as e:
        await status.edit_text(f"Feil: {e}")


async def cmd_selfcheck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """NEXUS leser sin egen system-prompt og rapporterer tilstand."""
    from pathlib import Path
    from tools.ruflo_tool import get_memory_stats

    prompt_paths = [
        Path("/opt/nexus/master_agent_system_prompt.txt"),
        Path(__file__).parent.parent / "master_agent_system_prompt.txt",
    ]
    prompt_preview = "Ikke funnet"
    for p in prompt_paths:
        if p.exists():
            content = p.read_text(encoding="utf-8")
            prompt_preview = content[:300] + "..." if len(content) > 300 else content
            break

    mem_stats = get_memory_stats()
    entries = mem_stats.get("output", "").split("Total Entries")[1].split("|")[1].strip() if "Total Entries" in mem_stats.get("output", "") else "?"

    report = (
        f"NEXUS Selvsjekk — {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Model: claude-sonnet-4-6\n"
        f"Server: Hetzner 89.167.100.7\n"
        f"Ruflo minne: {entries} entries\n\n"
        f"System-prompt (første 300 tegn):\n{prompt_preview}"
    )
    await update.message.reply_text(report[:3000])


# ---------------------------------------------------------------------------
# Tekstmeldinger med hukommelse
# ---------------------------------------------------------------------------

def _needs_web_search(text: str) -> bool:
    """Sjekk om meldingen trenger web-søk."""
    keywords = [
        "søk", "finn", "hva er", "hva skjer", "news", "nyheter", "trend",
        "hvordan går det med", "se på", "analyser", "research", "sjekk",
        "ai news", "hva sier", "hvem er", "scan", "les om", "se gjennom",
        "fortell meg", "github", "hvem bygger", "hva gjør",
    ]
    text_lower = text.lower()
    return any(k in text_lower for k in keywords)


def _has_urls(text: str) -> list:
    """Finn alle URLs i tekst."""
    import re
    return re.findall(r'https?://[^\s\)\]\>\"\']+', text)


async def _send_long(update, text: str) -> None:
    """Send tekst, splitter ved 4000 tegn."""
    for i in range(0, len(text), 4000):
        chunk = text[i:i + 4000]
        try:
            await update.message.reply_text(chunk, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(chunk)


async def cmd_worker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Spawn en spesialisert arbeider: /worker [type] [oppgave]"""
    args = context.args or []
    valid = ["research", "sales", "content", "code", "analytics", "memory"]
    if not args or args[0].lower() not in valid:
        await update.message.reply_text(
            "Bruk: /worker [type] [oppgave]\n\n"
            "Typer:\n"
            "  research  — søk/analyse\n"
            "  sales     — leads/Brreg\n"
            "  content   — Obsidian-notat\n"
            "  code      — kjør Python\n"
            "  analytics — SSB/Stripe\n"
            "  memory    — KG-oppdatering\n\n"
            "Eks: /worker research AI startups Norway 2025"
        )
        return
    specialty = args[0].lower()
    task = " ".join(args[1:]) if len(args) > 1 else "Utfør en standard oppgave"
    status_msg = await update.message.reply_text(f"Kjører {specialty}-arbeider...")
    try:
        import asyncio as _asyncio
        loop = _asyncio.get_event_loop()
        from workers.orchestrator import Orchestrator
        orch = Orchestrator()
        result = await loop.run_in_executor(None, lambda: orch.run_worker(specialty, task))
        ok = "OK" if result.get("success") else "FEIL"
        ms = result.get("duration_ms", 0)
        text = f"[{specialty.upper()} {ok} {ms}ms]\n\n{result.get('result', 'Ingen output')}"
        await status_msg.delete()
        await _send_long(update, text)
    except Exception as e:
        await status_msg.edit_text(f"Worker feil: {e}")


async def cmd_brain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Spør hjernesystemet: /brain [spørsmål]"""
    query = " ".join(context.args) if context.args else None
    if not query:
        await update.message.reply_text("Bruk: /brain [spørsmål]\nEks: /brain hvem er nicholas")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        import sys as _sys
        if '/opt/nexus' not in _sys.path:
            _sys.path.insert(0, '/opt/nexus')
        from memory.brain import Brain
        b = Brain()
        ctx = b.get_context(query)
        status = b.status()
        header = (
            f"Hjernesystem — {query}\n"
            f"KG: {status.get('knowledge_graph',{}).get('nodes',0)} noder | "
            f"Vektor: {status.get('vector_memory',{}).get('count',0)} minner | "
            f"Vault: {status.get('obsidian',{}).get('total_notes',0)} notater\n\n"
        )
        await _send_long(update, header + (ctx or "Ingen kontekst funnet."))
    except Exception as e:
        await update.message.reply_text(f"Brain feil: {e}")


async def cmd_kg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Søk i kunnskapsgrafen: /kg [søk]"""
    query = " ".join(context.args) if context.args else None
    if not query:
        await update.message.reply_text("Bruk: /kg [søk]\nEks: /kg AIDN bedrifter Bodø")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        import sys as _sys
        if '/opt/nexus' not in _sys.path:
            _sys.path.insert(0, '/opt/nexus')
        from memory.brain import Brain
        b = Brain()
        if not b.kg:
            await update.message.reply_text("KG ikke tilgjengelig.")
            return
        nodes = b.kg.search_nodes(query, limit=10)
        if not nodes:
            await update.message.reply_text(f"Ingen noder funnet for: {query}")
            return
        lines = [f"KG-søk: '{query}' → {len(nodes)} treff\n"]
        for n in nodes:
            lines.append(f"• [{n.get('type','?')}] {n.get('label','?')} (imp={n.get('importance',1)})")
            if n.get('attrs'):
                for k, v in list(n['attrs'].items())[:3]:
                    lines.append(f"    {k}: {v}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"KG feil: {e}")


async def cmd_delegate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deleger en kompleks jobb til orkestratoren: /delegate [oppgave]"""
    task = " ".join(context.args) if context.args else None
    if not task:
        await update.message.reply_text(
            "Bruk: /delegate [oppgave]\n"
            "Eks: /delegate Finn 10 IT-bedrifter i Bodø og skriv pitch til dem"
        )
        return
    status_msg = await update.message.reply_text(f"Orkestrerer: {task[:80]}...")
    try:
        import asyncio as _asyncio
        loop = _asyncio.get_event_loop()
        from workers.orchestrator import Orchestrator
        orch = Orchestrator()
        result = await loop.run_in_executor(None, lambda: orch.delegate(task))
        plan = result.get("plan", "")
        summary = result.get("summary", "")
        ms = result.get("duration_ms", 0)
        workers = ", ".join(result.get("workers_used", []))
        tokens = result.get("total_tokens", 0)
        text = (
            f"Delegert jobb fullført ({ms}ms, {tokens} tokens)\n"
            f"Arbeidere: {workers}\n\n"
            f"Plan: {plan}\n\n"
            f"Resultat:\n{summary}"
        )
        await status_msg.delete()
        await _send_long(update, text)
    except Exception as e:
        await status_msg.edit_text(f"Delegate feil: {e}")


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Søk på nettet — Perplexity eller DuckDuckGo fallback."""
    query = " ".join(context.args) if context.args else None
    if not query:
        await update.message.reply_text("Bruk: /search [søkeord]\nEks: /search jachal github")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        from tools.research_tool import search
        result = search(query)
        await _send_long(update, result)
    except Exception:
        # Fallback til DuckDuckGo
        try:
            from tools.ddg_search import search as ddg
            result = ddg(query)
            await _send_long(update, result)
        except Exception as e:
            await update.message.reply_text(f"Søk feilet: {e}")


async def cmd_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Les innholdet på en URL — GitHub, nettsider, Reddit."""
    url = context.args[0] if context.args else None
    if not url or not url.startswith("http"):
        await update.message.reply_text("Bruk: /url [lenke]\nEks: /url https://github.com/jachal")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    status = await update.message.reply_text("🔗 Leser lenken...")
    try:
        from tools.url_reader import read_url
        content = read_url(url)
        await status.delete()
        await _send_long(update, content)
    except Exception as e:
        await status.edit_text(f"❌ Kunne ikke lese: {e}")


async def cmd_github(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analyser GitHub-profil eller repo."""
    target = context.args[0] if context.args else None
    if not target:
        await update.message.reply_text("Bruk: /github [bruker eller url]\nEks: /github jachal")
        return
    if not target.startswith("http"):
        target = f"https://github.com/{target}"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    status = await update.message.reply_text("📦 Henter GitHub-info...")
    try:
        from tools.url_reader import read_url
        content = read_url(target)
        await status.delete()
        await _send_long(update, content)
    except Exception as e:
        await status.edit_text(f"❌ Feil: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _owner_chat_id
    if not _owner_chat_id:
        _owner_chat_id = str(update.effective_chat.id)

    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    from memory.conversation import save_message, load_recent
    history = load_recent(n=8)

    # Smart Memory: relevant kontekst (maks 500 tokens)
    smart_context = ""
    try:
        from memory.smart_memory import get_context
        smart_context = get_context(user_text, max_tokens=500)
    except Exception as e:
        logger.warning(f"smart_memory feilet: {e}")

    # Strategi-kontekst fra reflection_agent
    strategy_context = ""
    try:
        from agents.reflection_agent import get_current_strategy
        strategy_context = get_current_strategy()
    except Exception:
        pass

    # Kunnskapsbase
    kb_context = ""
    try:
        from memory.knowledge_base import query as kb_query
        kb_context = kb_query(user_text, top_k=3, max_chars=800)
    except Exception:
        pass

    # Brain system — KG + vektorminne + Obsidian (ny arkitektur)
    brain_context = ""
    try:
        import sys as _sys
        if '/opt/nexus' not in _sys.path:
            _sys.path.insert(0, '/opt/nexus')
        from memory.brain import Brain
        _brain = Brain()
        _raw = _brain.get_context(user_text)
        if _raw and len(_raw.strip()) > 20:
            brain_context = f"\n\n═══ HJERNESYSTEM (KG + Vektor + Vault) ═══\n{_raw[:1200]}"
    except Exception as _be:
        logger.debug(f"brain_context feilet: {_be}")

    system = NEXUS_TELEGRAM_SYSTEM + smart_context + strategy_context + kb_context + brain_context

    # Bygg meldingsliste (Anthropic format)
    messages = []
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_text})

    try:
        # Function calling loop — NEXUS bruker verktøy til den er ferdig
        MAX_TOOL_ROUNDS = 5
        for _ in range(MAX_TOOL_ROUNDS):
            response = anthropic_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=system,
                tools=NEXUS_TOOLS,
                messages=messages,
            )

            if response.stop_reason != "tool_use":
                break

            # Vis "jobber..." mens verktøy brukes
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action="typing"
            )

            # Utfør alle verktøykall
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await _execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result)[:4000],
                    })
                    logger.info(f"Tool: {block.name}({block.input}) → {str(result)[:80]}")

            # Legg til assistent-svar + verktøy-resultater
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        # Trekk ut endelig tekstsvar
        reply = ""
        for block in response.content:
            if hasattr(block, "text"):
                reply += block.text

        if not reply:
            reply = "Kjørte verktøy, men fikk ikke tekstsvar. Prøv igjen."

        save_message("user", user_text)
        save_message("assistant", reply)

        await _send_long(update, reply)

    except Exception as e:
        logger.error(f"Telegram LLM feil: {e}", exc_info=True)
        await update.message.reply_text(f"Teknisk feil: {e}")


# ---------------------------------------------------------------------------
# Bildeanalyse (Claude vision)
# ---------------------------------------------------------------------------

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _owner_chat_id
    if not _owner_chat_id:
        _owner_chat_id = str(update.effective_chat.id)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    caption = update.message.caption or "Hva er dette? Analyser og si hva du tenker."

    # Last ned bildet
    photo = update.message.photo[-1]  # Høyest oppløsning
    file = await context.bot.get_file(photo.file_id)
    photo_bytes = io.BytesIO()
    await file.download_to_memory(photo_bytes)
    photo_bytes.seek(0)
    image_b64 = base64.standard_b64encode(photo_bytes.read()).decode("utf-8")

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=NEXUS_TELEGRAM_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": caption},
                ],
            }],
        )
        reply = response.content[0].text

        from memory.conversation import save_message
        save_message("user", f"[BILDE] {caption}")
        save_message("assistant", reply)

        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"Bilde-analyse feil: {e}")
        await update.message.reply_text("Kunne ikke analysere bildet.")


# ---------------------------------------------------------------------------
# Dokumentanalyse (PDF, Word, tekst)
# ---------------------------------------------------------------------------

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analyser dokument sendt av Nicholas — PDF, Word, tekst, CSV."""
    global _owner_chat_id
    if not _owner_chat_id:
        _owner_chat_id = str(update.effective_chat.id)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    doc = update.message.document
    caption = update.message.caption or "Analyser dette dokumentet og gi meg de viktigste punktene."
    filename = doc.file_name or "dokument"
    mime = doc.mime_type or ""

    # Last ned filen
    file = await context.bot.get_file(doc.file_id)
    file_bytes = io.BytesIO()
    await file.download_to_memory(file_bytes)
    file_bytes.seek(0)
    raw = file_bytes.read()

    # Ekstraher tekst basert på filtype
    extracted_text = ""
    try:
        if mime == "application/pdf" or filename.endswith(".pdf"):
            extracted_text = _extract_pdf_text(raw)
        elif mime in ("text/plain", "text/csv") or filename.endswith((".txt", ".csv", ".md")):
            extracted_text = raw.decode("utf-8", errors="ignore")[:8000]
        elif "word" in mime or filename.endswith((".docx", ".doc")):
            extracted_text = _extract_docx_text(raw)
        else:
            # Prøv som ren tekst
            extracted_text = raw.decode("utf-8", errors="ignore")[:4000]
    except Exception as e:
        logger.error(f"Dokument-ekstraksjon feil: {e}")
        extracted_text = f"Kunne ikke lese fil: {filename}"

    if not extracted_text.strip():
        await update.message.reply_text(f"Kunne ikke lese innholdet i {filename}.")
        return

    prompt = (
        f"Dokument: {filename}\n"
        f"Instruksjon: {caption}\n\n"
        f"INNHOLD:\n{extracted_text[:6000]}"
    )

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=NEXUS_TELEGRAM_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        reply = response.content[0].text

        from memory.conversation import save_message
        save_message("user", f"[DOKUMENT: {filename}] {caption}")
        save_message("assistant", reply)

        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"Dokument-analyse LLM feil: {e}")
        await update.message.reply_text("Teknisk feil ved dokumentanalyse.")


def _extract_pdf_text(raw: bytes) -> str:
    """Ekstraher tekst fra PDF."""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages[:20])[:8000]
    except ImportError:
        pass
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages[:20])[:8000]
    except Exception:
        return ""


def _extract_docx_text(raw: bytes) -> str:
    """Ekstraher tekst fra Word-dokument."""
    try:
        import docx
        doc = docx.Document(io.BytesIO(raw))
        return "\n".join(p.text for p in doc.paragraphs)[:8000]
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Varsling til eier
# ---------------------------------------------------------------------------

async def send_alert(message: str):
    chat_id = _owner_chat_id or OWNER_CHAT_ID
    if not chat_id or not TELEGRAM_TOKEN:
        logger.warning("Telegram ikke konfigurert — kan ikke sende varsling")
        return
    bot = Bot(token=TELEGRAM_TOKEN)
    async with bot:
        await bot.send_message(chat_id=chat_id, text=message)


def notify_owner(message: str):
    try:
        asyncio.run(send_alert(message))
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.create_task(send_alert(message))


# ---------------------------------------------------------------------------
# App-bygging
# ---------------------------------------------------------------------------

def build_app():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN mangler i .env")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("leads", cmd_leads))
    app.add_handler(CommandHandler("email", cmd_email))
    app.add_handler(CommandHandler("mcp", cmd_mcp))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("forget", cmd_forget))
    app.add_handler(CommandHandler("memory", cmd_memory))
    app.add_handler(CommandHandler("goals", cmd_goals))
    app.add_handler(CommandHandler("reflect", cmd_reflect))
    app.add_handler(CommandHandler("replies", cmd_replies))
    app.add_handler(CommandHandler("browse", cmd_browse))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("url", cmd_url))
    app.add_handler(CommandHandler("github", cmd_github))
    app.add_handler(CommandHandler("selfcheck", cmd_selfcheck))
    app.add_handler(CommandHandler("worker", cmd_worker))
    app.add_handler(CommandHandler("brain", cmd_brain))
    app.add_handler(CommandHandler("kg", cmd_kg))
    app.add_handler(CommandHandler("delegate", cmd_delegate))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


def start_bot():
    logger.info("NEXUS Telegram-bot starter...")
    build_app().run_polling(drop_pending_updates=True)
