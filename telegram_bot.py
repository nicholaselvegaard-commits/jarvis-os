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
- Hjerne: Claude Sonnet 4.6 (LangGraph-orkestrasjon)
- Lead-gen: Apollo.io API (50 leads/dag)
- E-post: Instantly.ai (bulk outreach)
- Hukommelse: SQLite + Ruflo vektorminne
- Voice: Vapi.ai + ElevenLabs norsk stemme (uke 2)
- Web-søk: Perplexity API
- Kommunikasjon: MCP-board til Jordan, Telegram til Nicholas
- Cron-jobber: 06:00/08:00/12:00/18:00/20:00/23:00 (Oslo-tid)
Når Nicholas spør hva du er eller hva som er lagt til → svar med dette. Presist, ikke vagt.

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


# ---------------------------------------------------------------------------
# Kommandoer
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _owner_chat_id
    _owner_chat_id = str(update.effective_chat.id)
    logger.info(f"Telegram eier registrert: {_owner_chat_id}")
    await update.message.reply_text(
        "NEXUS online.\n\n"
        "Send en lenke direkte — jeg leser den automatisk.\n\n"
        "/search [søkeord] — søk på nettet\n"
        "/url [lenke] — les nettside eller GitHub\n"
        "/github [bruker] — analyser GitHub-profil\n"
        "/status — systemstatus\n"
        "/leads — hent nye leads nå\n"
        "/email — send e-poster nå\n"
        "/mcp — sjekk MCP-board\n"
        "/report — generer daglig rapport\n"
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
            from ddg_search import search as ddg
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
        from url_reader import read_url
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
        from url_reader import read_url
        content = read_url(target)
        await status.delete()
        await _send_long(update, content)
    except Exception as e:
        await status.edit_text(f"❌ Feil: {e}")


def _load_nexus_identity() -> str:
    """
    Les NEXUS sitt eget minne fra Ruflo og bygg en identitetskontekst.
    Injiseres i hver melding så NEXUS vet hva den har gjort og hvem den er.
    """
    try:
        from tools.ruflo_tool import memory_search, memory_list
        recent = memory_list(limit=5)
        if not recent:
            recent = memory_search("nexus campaign lead", limit=5)

        if recent:
            lines = []
            for entry in recent[:5]:
                val = entry.get("value", entry.get("preview", str(entry)))[:120]
                lines.append(f"- {val}")
            return "\n[NEXUS HUKOMMELSE — hva du har gjort]:\n" + "\n".join(lines)
    except Exception:
        pass
    return ""


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _owner_chat_id
    if not _owner_chat_id:
        _owner_chat_id = str(update.effective_chat.id)

    user_text = update.message.text
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    from memory.conversation import save_message, load_recent
    history = load_recent(n=8)

    # Inject NEXUS sin Ruflo-hukommelse + lærdomsverdier — gir identitet og kontinuitet
    identity_context = _load_nexus_identity()
    try:
        from memory.self_learning import get_learnings_for_prompt
        identity_context += get_learnings_for_prompt()
    except Exception:
        pass

    # Auto-les URLer i meldingen
    url_context = ""
    detected_urls = _has_urls(user_text)
    if detected_urls:
        try:
            from url_reader import read_url
            url_parts = []
            for u in detected_urls[:2]:
                content = read_url(u, max_chars=2500)
                url_parts.append(f"[Innhold fra {u}]:\n{content}")
            if url_parts:
                url_context = "\n\n[URL-INNHOLD HENTET AUTOMATISK]:\n" + "\n\n".join(url_parts)
        except Exception as e:
            logger.warning(f"URL-lesing feilet: {e}")

    # Automatisk web-søk hvis meldingen krever fersk data
    web_context = ""
    if _needs_web_search(user_text) and not detected_urls:
        try:
            from tools.research_tool import search
            web_context = search(user_text)
            web_context = f"\n\n[FERSK DATA FRA NETTET]:\n{web_context[:1500]}"
        except Exception:
            try:
                from ddg_search import search as ddg
                web_context = ddg(user_text)
                web_context = f"\n\n[FERSK DATA FRA NETTET (DDG)]:\n{web_context[:1500]}"
            except Exception as e:
                logger.warning(f"Web-søk feilet: {e}")

    # Bygg meldingsliste til LLM
    system_with_memory = NEXUS_TELEGRAM_SYSTEM + identity_context
    messages = [SystemMessage(content=system_with_memory)]
    for msg in history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))

    full_input = user_text + url_context + web_context
    messages.append(HumanMessage(content=full_input))

    try:
        response = llm.invoke(messages)
        reply = response.content

        save_message("user", user_text)
        save_message("assistant", reply)

        await _send_long(update, reply)
    except Exception as e:
        logger.error(f"Telegram LLM feil: {e}")
        await update.message.reply_text("Teknisk feil — prøv igjen.")


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
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("url", cmd_url))
    app.add_handler(CommandHandler("github", cmd_github))
    app.add_handler(CommandHandler("selfcheck", cmd_selfcheck))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


def start_bot():
    logger.info("NEXUS Telegram-bot starter...")
    build_app().run_polling(drop_pending_updates=True)
