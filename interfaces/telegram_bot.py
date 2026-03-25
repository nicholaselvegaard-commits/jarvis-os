"""
NEXUS Telegram Bot — Jordan's bot.py adapted for the NEXUS structure.

Uses core.engine for the AI loop (Jordan's full tool suite + NEXUS smart_memory).
Keeps ALL Jordan commands + adds NEXUS-specific ones (/goals, /reflect, /replies, /memory).
"""
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv(Path(__file__).parent.parent / ".env")

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import core.engine as engine
import tools.email_sender as email_sender

logger = logging.getLogger(__name__)

BASE_DIR             = Path(__file__).parent.parent
PENDING_ACTIONS_FILE = BASE_DIR / "memory" / "pending_actions.json"
VOICE_MODE_FILE      = BASE_DIR / "memory" / "voice_mode.json"
MODEL_FILE           = BASE_DIR / "memory" / "model_pref.json"

ALLOWED_CHAT_IDS: set[str] = set(
    x.strip() for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip()
)

MODELS = {
    "claude": "claude-sonnet-4-6",
    "haiku":  "claude-haiku-4-5-20251001",
    "groq":   "groq",
    "gemini": "gemini",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_model(chat_id: str) -> str:
    if MODEL_FILE.exists():
        try:
            return json.loads(MODEL_FILE.read_text(encoding="utf-8")).get(chat_id, "claude")
        except Exception:
            pass
    return "claude"


def _set_model(chat_id: str, model: str) -> None:
    data: dict = {}
    if MODEL_FILE.exists():
        try:
            data = json.loads(MODEL_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    data[chat_id] = model
    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODEL_FILE.write_text(json.dumps(data), encoding="utf-8")


def _get_voice_mode(chat_id: str) -> bool:
    if VOICE_MODE_FILE.exists():
        try:
            return json.loads(VOICE_MODE_FILE.read_text(encoding="utf-8")).get(chat_id, False)
        except Exception:
            pass
    return False


def _set_voice_mode(chat_id: str, enabled: bool) -> None:
    data: dict = {}
    if VOICE_MODE_FILE.exists():
        try:
            data = json.loads(VOICE_MODE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    data[chat_id] = enabled
    VOICE_MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    VOICE_MODE_FILE.write_text(json.dumps(data), encoding="utf-8")


def _load_pending() -> dict:
    if PENDING_ACTIONS_FILE.exists():
        try:
            return json.loads(PENDING_ACTIONS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


def _save_pending(actions: dict) -> None:
    PENDING_ACTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_ACTIONS_FILE.write_text(json.dumps(actions, indent=2, ensure_ascii=False), encoding="utf-8")


def _is_allowed(update: Update) -> bool:
    chat_id = str(update.effective_chat.id)
    if not ALLOWED_CHAT_IDS:
        return True
    return chat_id in ALLOWED_CHAT_IDS


async def _send_long(update: Update, text: str, parse_mode: str = ParseMode.MARKDOWN) -> None:
    limit = 4000
    for i in range(0, len(text), limit):
        chunk = text[i:i + limit]
        try:
            await update.message.reply_text(chunk, parse_mode=parse_mode)
        except Exception:
            await update.message.reply_text(chunk)


async def _send(
    chat_id: str,
    text: str,
    reply_markup: dict | None = None,
    application: Application | None = None,
) -> None:
    markup = None
    if reply_markup:
        keyboard = [
            [InlineKeyboardButton(btn["text"], callback_data=btn["callback_data"]) for btn in row]
            for row in reply_markup["inline_keyboard"]
        ]
        markup = InlineKeyboardMarkup(keyboard)
    await application.bot.send_message(
        chat_id=int(chat_id),
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=markup,
    )


async def _send_voice_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    try:
        import tools.jarvis_voice as jarvis_voice
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.RECORD_VOICE
        )
        audio_path = jarvis_voice.speak(text)
        with open(audio_path, "rb") as f:
            await update.message.reply_voice(voice=f, caption=text[:1024])
        jarvis_voice.cleanup_old_voice_files()
    except Exception as e:
        logger.warning(f"Voice reply failed: {e}")
        try:
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await update.message.reply_text(text)


# ── Command handlers ───────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    await update.message.reply_text(
        "👋 Hei! Jeg er Jarvis (NEXUS) — din personlige AI-agent.\n\n"
        "Bare skriv hva du vil — jeg skjønner kontekst, leser lenker og søker på nett.\n\n"
        "*Jordans kommandoer:*\n"
        "/search [søkeord] — søk på nettet\n"
        "/url [lenke] — les innhold fra nettside\n"
        "/github [bruker/repo] — analyser GitHub-profil\n"
        "/model — bytt AI-modell\n"
        "/ring — Jarvis svarer med stemme\n"
        "/voicemode — toggle stemme-modus\n"
        "/ny — nullstill samtalehistorikk\n"
        "/pending — vis ventende e-postgodkjenninger\n\n"
        "*NEXUS kommandoer:*\n"
        "/goals — vis mål-progress (100 000 NOK)\n"
        "/reflect — kjør selvrefleksjon og oppdater strategi\n"
        "/replies — sjekk e-postsvar fra leads\n"
        "/memory — vis smart memory-status\n"
        "/browse [url] — browser-automatisering",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_ny(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    chat_id = str(update.effective_chat.id)
    engine.clear_history(chat_id)
    await update.message.reply_text("🔄 Samtalehistorikk nullstilt.")


async def cmd_ring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    chat_id = str(update.effective_chat.id)
    await context.bot.send_chat_action(chat_id=int(chat_id), action=ChatAction.RECORD_VOICE)

    async def telegram_send(to_chat_id: str, text: str, reply_markup: dict | None = None) -> None:
        await _send(to_chat_id, text, reply_markup, application=context.application)

    response = await engine.run(
        user_message="[RING] Nicholas ringer deg. Svar som om du tar telefonen — kort, energisk, fortell hva du jobber med akkurat nå. Maks 3-4 setninger. Snakk norsk.",
        chat_id=chat_id,
        telegram_send=telegram_send,
    )
    if response:
        await _send_voice_reply(update, context, response)


async def cmd_voicemode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    chat_id = str(update.effective_chat.id)
    current = _get_voice_mode(chat_id)
    _set_voice_mode(chat_id, not current)
    status = "🔊 Stemme-modus PÅ" if not current else "💬 Stemme-modus AV"
    await update.message.reply_text(status)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    query = " ".join(context.args) if context.args else None
    if not query:
        await update.message.reply_text("Bruk: /search [søkeord]")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        try:
            import tools.web_search as ws
            results = ws.search(query, num_results=5)
            text = f"🔍 *Søk: {query}*\n\n"
            for r in results:
                text += f"*{r.title}*\n{r.url}\n{r.snippet[:200]}\n\n"
        except Exception:
            import tools.ddg_search as ddg
            text = ddg.search(query, max_results=5)
        await _send_long(update, text)
    except Exception as e:
        await update.message.reply_text(f"❌ Søk feilet: {e}")


async def cmd_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    url = context.args[0] if context.args else None
    if not url or not url.startswith("http"):
        await update.message.reply_text("Bruk: /url [lenke]")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    status = await update.message.reply_text("🔗 Leser lenken...")
    try:
        import tools.url_reader as url_reader
        content = url_reader.read_url(url)
        await status.delete()
        await _send_long(update, content)
    except Exception as e:
        await status.edit_text(f"❌ Kunne ikke lese URL: {e}")


async def cmd_github(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    target = context.args[0] if context.args else None
    if not target:
        await update.message.reply_text("Bruk: /github [bruker eller url]")
        return
    if not target.startswith("http"):
        target = f"https://github.com/{target}"
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    status = await update.message.reply_text("📦 Henter GitHub-info...")
    try:
        import tools.url_reader as url_reader
        content = url_reader.read_url(target)
        await status.delete()
        await _send_long(update, content)
    except Exception as e:
        await status.edit_text(f"❌ Feil: {e}")


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    chat_id = str(update.effective_chat.id)
    if not context.args:
        current = _get_model(chat_id)
        model_list = "\n".join(f"  {'→' if k == current else ' '} `{k}` — {v}" for k, v in MODELS.items())
        await update.message.reply_text(
            f"🤖 *Aktiv modell:* `{current}`\n\n*Tilgjengelige:*\n{model_list}\n\nBruk: `/model claude`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    chosen = context.args[0].lower()
    if chosen not in MODELS:
        await update.message.reply_text(f"Ukjent modell. Velg: {', '.join(MODELS.keys())}")
        return
    _set_model(chat_id, chosen)
    await update.message.reply_text(f"✅ Modell byttet til `{chosen}`", parse_mode=ParseMode.MARKDOWN)


async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    actions = _load_pending()
    pending = {k: v for k, v in actions.items() if v.get("status") == "pending"}
    if not pending:
        await update.message.reply_text("✅ Ingen ventende godkjenninger.")
        return
    for action_id, action in pending.items():
        text = (
            f"📧 *Ventende e-post* — ID: `{action_id}`\n"
            f"*Til:* {action['to']}\n"
            f"*Emne:* {action['subject']}\n\n"
            f"```\n{action['body'][:500]}\n```"
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Send", callback_data=f"send_email:{action_id}"),
            InlineKeyboardButton("❌ Avbryt", callback_data=f"cancel_email:{action_id}"),
        ]])
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


# ── NEXUS commands ────────────────────────────────────────────────────────────

async def cmd_goals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vis mål-progress mot 100 000 NOK."""
    if not _is_allowed(update):
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        from memory.goals import format_for_telegram
        text = format_for_telegram()
    except Exception as e:
        text = f"❌ Kunne ikke hente mål: {e}"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_reflect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kjør selvrefleksjon og oppdater strategi."""
    if not _is_allowed(update):
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    status = await update.message.reply_text("🔄 Kjører selvrefleksjon...")
    try:
        from agents.reflection_agent import reflect_sync
        result = reflect_sync()
        await status.delete()
        await _send_long(update, f"🧠 *Selvrefleksjon fullført*\n\n{result}")
    except Exception as e:
        await status.edit_text(f"❌ Refleksjon feilet: {e}")


async def cmd_replies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sjekk e-postsvar fra leads."""
    if not _is_allowed(update):
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    try:
        from tools.email_reader import format_replies_for_nexus
        text = format_replies_for_nexus(days=3)
    except Exception as e:
        text = f"❌ Kunne ikke sjekke svar: {e}\n\nSett opp IMAP_HOST, EMAIL_ADDRESS, EMAIL_PASSWORD i .env"
    await _send_long(update, text)


async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vis smart memory-status."""
    if not _is_allowed(update):
        return
    try:
        from memory.smart_memory import stats as get_stats
        stats = get_stats()
        text = (
            f"🧠 *Smart Memory Status*\n\n"
            f"Total entries: {stats.get('total', 0)}\n"
            f"Kategorier: {', '.join(stats.get('categories', {}).keys()) or 'ingen'}\n"
            f"Siste 24t: {stats.get('recent_24h', 0)}"
        )
    except Exception as e:
        text = f"❌ Memory feil: {e}"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_todo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vis Nicholas sin TODO-liste — hva som mangler og hva som må gjøres."""
    if not _is_allowed(update):
        return
    todo_path = BASE_DIR / "memory" / "nicholas_todo.md"
    if not todo_path.exists():
        await update.message.reply_text("Ingen TODO-liste ennå.")
        return
    content = todo_path.read_text(encoding="utf-8")
    # Send i bolker hvis for lang
    if len(content) > 4000:
        for i in range(0, len(content), 4000):
            await update.message.reply_text(content[i:i+4000])
    else:
        await update.message.reply_text(content)


async def cmd_browse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Browser-automatisering."""
    if not _is_allowed(update):
        return
    url = context.args[0] if context.args else None
    if not url or not url.startswith("http"):
        await update.message.reply_text("Bruk: /browse [url]")
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    status = await update.message.reply_text("🌐 Åpner browser...")
    try:
        from tools.browser import browse
        result = await browse(url=url, task="read")
        await status.delete()
        await _send_long(update, result[:4000])
    except Exception as e:
        await status.edit_text(f"❌ Browser feilet: {e}")


# ── Voice handler ──────────────────────────────────────────────────────────────

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    chat_id = str(update.effective_chat.id)
    voice = update.message.voice or update.message.audio

    await context.bot.send_chat_action(chat_id=int(chat_id), action=ChatAction.TYPING)
    status_msg = await update.message.reply_text("🎙️ Transkriberer...")

    voice_file = await context.bot.get_file(voice.file_id)
    tmp_path = BASE_DIR / "memory" / f"voice_{voice.file_id}.ogg"
    try:
        await voice_file.download_to_drive(str(tmp_path))
        import tools.voice_transcriber as vt
        text = vt.transcribe(str(tmp_path))
        if not text:
            await status_msg.edit_text("⚠️ Klarte ikke å transkribere lyden.")
            return

        await status_msg.edit_text(f"🎙️ *Hørte:* _{text}_", parse_mode=ParseMode.MARKDOWN)

        async def telegram_send(to_chat_id: str, msg_text: str, reply_markup: dict | None = None) -> None:
            await _send(to_chat_id, msg_text, reply_markup, application=context.application)

        response = await engine.run(
            user_message=text,
            chat_id=chat_id,
            telegram_send=telegram_send,
        )
        if response:
            await _send_voice_reply(update, context, response)
    except Exception as e:
        logger.error(f"Voice handler error: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Feil: {e}")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# ── Message handler ────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        chat_id = str(update.effective_chat.id)
        await update.message.reply_text(
            f"⛔ Ikke autorisert.\n\nDin chat-ID: `{chat_id}`\n"
            f"Legg til i `.env` under `ALLOWED_CHAT_IDS`.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    chat_id = str(update.effective_chat.id)
    user_text = update.message.text.strip()

    await context.bot.send_chat_action(chat_id=int(chat_id), action=ChatAction.TYPING)

    # Auto-detect URLs and fetch content
    url_context = ""
    try:
        import tools.url_reader as url_reader
        detected_urls = url_reader.extract_urls(user_text)
        if detected_urls:
            status_msg = await update.message.reply_text(f"🔗 Leser {len(detected_urls)} lenke(r)...")
            url_parts = []
            for u in detected_urls[:2]:
                try:
                    content = url_reader.read_url(u, max_chars=2500)
                    url_parts.append(f"[Innhold fra {u}]:\n{content}")
                except Exception:
                    pass
            if url_parts:
                url_context = "\n\n" + "\n\n".join(url_parts)
            try:
                await status_msg.delete()
            except Exception:
                pass
    except Exception:
        pass

    async def telegram_send(to_chat_id: str, text: str, reply_markup: dict | None = None) -> None:
        await _send(to_chat_id, text, reply_markup, application=context.application)

    try:
        full_message = user_text + url_context
        response = await engine.run(
            user_message=full_message,
            chat_id=chat_id,
            telegram_send=telegram_send,
        )
        if response:
            if _get_voice_mode(chat_id):
                await _send_voice_reply(update, context, response)
            else:
                await _send_long(update, response)
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Noe gikk galt: {e}")


# ── Callback handler (email approvals) ────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    chat_id = str(query.message.chat_id)

    if data.startswith("send_email:"):
        action_id = data.split(":", 1)[1]
        actions = _load_pending()
        action = actions.get(action_id)

        if not action:
            await query.edit_message_text("⚠️ Finner ikke denne e-posten.")
            return
        if action["status"] != "pending":
            await query.edit_message_text(f"ℹ️ E-post er allerede {action['status']}.")
            return

        try:
            email_sender.send_email(
                to=action["to"],
                subject=action["subject"],
                body=action["body"],
            )
            action["status"] = "sent"
            action["sent_at"] = datetime.now(timezone.utc).isoformat()
            follow_up_days = action.get("follow_up_days", 0)
            if follow_up_days > 0:
                action["follow_up_due"] = (
                    datetime.now(timezone.utc) + timedelta(days=follow_up_days)
                ).isoformat()
            _save_pending(actions)
            msg = f"✅ E-post sendt til *{action['to']}*!"
            if follow_up_days > 0:
                msg += f"\n⏰ Follow-up om {follow_up_days} dager."
            await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            await query.edit_message_text(f"❌ Klarte ikke å sende: `{e}`", parse_mode=ParseMode.MARKDOWN)

    elif data.startswith("cancel_email:"):
        action_id = data.split(":", 1)[1]
        actions = _load_pending()
        if action_id in actions:
            actions[action_id]["status"] = "cancelled"
            _save_pending(actions)
        await query.edit_message_text("❌ E-post avbrutt.")


# ── Follow-up scheduler ────────────────────────────────────────────────────────

async def check_follow_ups(application: Application) -> None:
    actions = _load_pending()
    now = datetime.now(timezone.utc)
    changed = False

    for action_id, action in actions.items():
        if action.get("type") != "email":
            continue
        if action.get("status") != "sent" or action.get("follow_up_sent"):
            continue
        due_str = action.get("follow_up_due")
        if not due_str:
            continue

        due = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
        if now >= due:
            follow_up_id = f"{action_id}_followup"
            follow_up_body = (
                f"Hei igjen,\n\n"
                f"Sender en oppfølging på min forrige e-post angående {action['subject']}.\n\n"
                f"Har du hatt mulighet til å se på dette?\n\n"
                f"Med vennlig hilsen"
            )
            actions[follow_up_id] = {
                "type": "email",
                "status": "pending",
                "to": action["to"],
                "subject": f"Re: {action['subject']}",
                "body": follow_up_body,
                "follow_up_days": 0,
                "chat_id": action["chat_id"],
                "created_at": now.isoformat().replace("+00:00", "Z"),
                "sent_at": None,
                "follow_up_sent": False,
                "is_follow_up": True,
            }
            action["follow_up_sent"] = True
            changed = True

            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Send follow-up", callback_data=f"send_email:{follow_up_id}"),
                InlineKeyboardButton("❌ Avbryt", callback_data=f"cancel_email:{follow_up_id}"),
            ]])
            try:
                await application.bot.send_message(
                    chat_id=int(action["chat_id"]),
                    text=f"⏰ *Follow-up klar*\n\nTil: {action['to']}\nEmne: Re: {action['subject']}",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard,
                )
            except Exception as e:
                logger.error(f"Follow-up notification failed: {e}")

    if changed:
        _save_pending(actions)


# ── Startup health check ───────────────────────────────────────────────────────

async def _startup_health_check(app: Application) -> None:
    import anthropic as _anthropic

    chat_ids = list(ALLOWED_CHAT_IDS)
    if not chat_ids:
        logger.warning("No ALLOWED_CHAT_IDS — skipping startup health check")
        return

    chat_id = chat_ids[0]
    problems = []
    ok = []

    try:
        c = _anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
        await c.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": "hi"}],
        )
        ok.append("Claude ✅")
    except _anthropic.AuthenticationError:
        problems.append("❌ ANTHROPIC_API_KEY ugyldig — Jarvis kjører på Groq-backup")
    except Exception as e:
        problems.append(f"⚠️ Claude: {e}")

    try:
        from tools.groq_client import chat as groq_chat
        groq_chat(prompt="hi", system="say hi", max_tokens=5)
        ok.append("Groq ✅")
    except Exception as e:
        problems.append(f"❌ Groq: {e}")

    ok.append("Telegram ✅")

    status_lines = "\n".join(ok + problems)
    msg = f"🤖 *Jarvis (NEXUS) startet*\n\n{status_lines}"
    if problems:
        msg += "\n\n⚠️ Fiks problemer for full funksjonalitet."

    try:
        await app.bot.send_message(chat_id=int(chat_id), text=msg, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Could not send startup message: {e}")


# ── Entry point ────────────────────────────────────────────────────────────────

def build_app() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

    app = Application.builder().token(token).post_init(_startup_health_check).build()

    # Jordan's original commands
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("ny",        cmd_ny))
    app.add_handler(CommandHandler("pending",   cmd_pending))
    app.add_handler(CommandHandler("ring",      cmd_ring))
    app.add_handler(CommandHandler("voicemode", cmd_voicemode))
    app.add_handler(CommandHandler("search",    cmd_search))
    app.add_handler(CommandHandler("url",       cmd_url))
    app.add_handler(CommandHandler("github",    cmd_github))
    app.add_handler(CommandHandler("model",     cmd_model))

    # NEXUS commands
    app.add_handler(CommandHandler("goals",   cmd_goals))
    app.add_handler(CommandHandler("reflect", cmd_reflect))
    app.add_handler(CommandHandler("replies", cmd_replies))
    app.add_handler(CommandHandler("memory",  cmd_memory))
    app.add_handler(CommandHandler("browse",  cmd_browse))

    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(CallbackQueryHandler(handle_callback))

    return app
