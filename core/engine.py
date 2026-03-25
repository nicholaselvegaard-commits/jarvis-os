"""
NEXUS Core Engine — Jordan's brain adapted for NEXUS.

Jordan's complete tool-use loop + NEXUS smart_memory injection.
Receives a message, runs the Claude tool-use loop, returns final text.
Tools that need user approval (e.g. email) store a pending action and
trigger a Telegram notification via callback.
"""
import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR          = Path(__file__).parent.parent
PENDING_ACTIONS_FILE = BASE_DIR / "memory" / "pending_actions.json"
CONVERSATIONS_DIR    = BASE_DIR / "memory" / "conversations"
AGENT_CONFIG_DIR     = BASE_DIR / "agents"
CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────────────────
CLAUDE_SONNET       = "claude-sonnet-4-6"
CLAUDE_HAIKU        = "claude-haiku-4-5-20251001"
MAX_API_HISTORY     = 8
CIRCUIT_BREAKER_THRESHOLD = 10
CIRCUIT_BREAKER_COOLDOWN  = 300  # seconds

_consecutive_errors: int = 0
_circuit_open_until: float = 0.0

TelegramSendFn = Callable[[str, str, dict | None], Awaitable[None]]


# ── Lazy tool imports (graceful fallback if not configured) ───────────────────
def _import_tools():
    """Import all tools — any that fail are silently replaced with stubs."""
    tools = {}
    try:
        import tools.web_search as m; tools["web_search"] = m
    except Exception: tools["web_search"] = None
    try:
        import tools.scraper as m; tools["scraper"] = m
    except Exception: tools["scraper"] = None
    try:
        import tools.browser as m; tools["browser"] = m
    except Exception: tools["browser"] = None
    try:
        import tools.email_sender as m; tools["email_sender"] = m
    except Exception: tools["email_sender"] = None
    try:
        import tools.email_reader as m; tools["email_reader"] = m
    except Exception: tools["email_reader"] = None
    try:
        import tools.memory_manager as m; tools["memory_manager"] = m
    except Exception: tools["memory_manager"] = None
    try:
        import tools.calendar as m; tools["calendar"] = m
    except Exception: tools["calendar"] = None
    try:
        import tools.instagram as m; tools["instagram"] = m
    except Exception: tools["instagram"] = None
    try:
        import tools.gmail as m; tools["gmail"] = m
    except Exception: tools["gmail"] = None
    try:
        import tools.teams as m; tools["teams"] = m
    except Exception: tools["teams"] = None
    try:
        import tools.stripe as m; tools["stripe"] = m
    except Exception: tools["stripe"] = None
    try:
        import tools.tiktok as m; tools["tiktok"] = m
    except Exception: tools["tiktok"] = None
    try:
        import tools.jarvis_notebook as m; tools["notebook"] = m
    except Exception: tools["notebook"] = None
    try:
        import tools.account_registry as m; tools["account_registry"] = m
    except Exception: tools["account_registry"] = None
    try:
        import tools.gemini_client as m; tools["gemini"] = m
    except Exception: tools["gemini"] = None
    try:
        import tools.perplexity_client as m; tools["perplexity"] = m
    except Exception: tools["perplexity"] = None
    try:
        import tools.supabase_client as m; tools["supabase"] = m
    except Exception: tools["supabase"] = None
    try:
        import tools.make_client as m; tools["make"] = m
    except Exception: tools["make"] = None
    try:
        import tools.jarvis_email as m; tools["jarvis_email"] = m
    except Exception: tools["jarvis_email"] = None
    try:
        import tools.github_client as m; tools["github"] = m
    except Exception: tools["github"] = None
    try:
        import tools.file_manager as m; tools["file_manager"] = m
    except Exception: tools["file_manager"] = None
    try:
        import tools.shell_runner as m; tools["shell"] = m
    except Exception: tools["shell"] = None
    try:
        import tools.url_reader as m; tools["url_reader"] = m
    except Exception: tools["url_reader"] = None
    try:
        import tools.google_trends as m; tools["google_trends"] = m
    except Exception: tools["google_trends"] = None
    try:
        import tools.twitter as m; tools["twitter"] = m
    except Exception: tools["twitter"] = None
    try:
        import tools.reddit as m; tools["reddit"] = m
    except Exception: tools["reddit"] = None
    try:
        import tools.elevenlabs as m; tools["elevenlabs"] = m
    except Exception: tools["elevenlabs"] = None
    try:
        import tools.gumroad as m; tools["gumroad"] = m
    except Exception: tools["gumroad"] = None
    try:
        import tools.vercel as m; tools["vercel"] = m
    except Exception: tools["vercel"] = None
    try:
        import tools.image_gen as m; tools["image_gen"] = m
    except Exception: tools["image_gen"] = None
    try:
        import tools.apollo as m; tools["apollo"] = m
    except Exception: tools["apollo"] = None
    try:
        import tools.news_fetcher as m; tools["news_fetcher"] = m
    except Exception: tools["news_fetcher"] = None
    try:
        import tools.arxiv as m; tools["arxiv"] = m
    except Exception: tools["arxiv"] = None
    try:
        import tools.coingecko as m; tools["coingecko"] = m
    except Exception: tools["coingecko"] = None
    try:
        import tools.minimax as m; tools["minimax"] = m
    except Exception: tools["minimax"] = None
    try:
        import tools.brreg as m; tools["brreg"] = m
    except Exception: tools["brreg"] = None
    try:
        import tools.github_tools as m; tools["github"] = m
    except Exception: tools["github"] = None
    return tools


_tools_cache = None

def _get_tools() -> dict:
    global _tools_cache
    if _tools_cache is None:
        _tools_cache = _import_tools()
    return _tools_cache


# ── System prompt ─────────────────────────────────────────────────────────────

def _load_agent_prompt(agent_name: str = "jordan") -> str:
    """Load system prompt from agents/<name>/system_prompt.txt"""
    path = AGENT_CONFIG_DIR / agent_name / "system_prompt.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning(f"System prompt not found: {path}")
    return "Du er Jarvis, Nicholas sin AI-agent."


def _active_integrations() -> str:
    checks = {
        "Stripe (betalinger)":      "STRIPE_SECRET_KEY",
        "Telegram (bot)":           "TELEGRAM_BOT_TOKEN",
        "Anthropic/Claude":         "ANTHROPIC_API_KEY",
        "Groq":                     "GROQ_API_KEY",
        "OpenRouter":               "OPENROUTER_API_KEY",
        "Perplexity":               "PERPLEXITY_API_KEY",
        "Gemini":                   "GEMINI_API_KEY",
        "ElevenLabs (TTS)":         "ELEVENLABS_API_KEY",
        "Gumroad":                  "GUMROAD_ACCESS_TOKEN",
        "GitHub":                   "GITHUB_TOKEN",
        "Vercel":                   "VERCEL_TOKEN",
        "Make.com":                 "MAKE_API_KEY",
        "Alchemy (Web3)":           "ALCHEMY_API_KEY",
        "Hunter.io (leads)":        "HUNTER_API_KEY",
        "Brave Search":             "BRAVE_API_KEY",
        "Tavily (agent search)":    "TAVILY_API_KEY",
        "NewsAPI":                  "NEWSAPI_KEY",
        "Gmail/SMTP":               "EMAIL_ADDRESS",
        "Supabase":                 "SUPABASE_URL",
        "Resend (e-post)":          "RESEND_API_KEY",
        "VAPI (stemme)":            "VAPI_API_KEY",
        "Apollo (leads)":           "APOLLO_API_KEY",
        "Twitter/X":                "TWITTER_BEARER_TOKEN",
        "OpenAI (DALL-E)":          "OPENAI_API_KEY",
        "Deepseek":                 "DEEPSEEK_API_KEY",
        "Pexels (bilder)":          "PEXELS_API_KEY",
        "Exchange Rate":            "EXCHANGE_RATE_API_KEY",
        "Product Hunt":             "PRODUCT_HUNT_TOKEN",
        "Firecrawl":                "FIRECRAWL_API_KEY",
        "E2B (sandkasse)":          "E2B_API_KEY",
        "HuggingFace":              "HUGGINGFACE_API_KEY",
        "MiniMax (LLM+TTS+Video)":  "MINIMAX_API_KEY",
    }
    # Brønnøysund er alltid aktiv (ingen key)
    active = [name for name, key in checks.items() if os.getenv(key)]
    if not active:
        return ""
    return (
        "\nTILGJENGELIGE INTEGRASJONER (API-keys er konfigurert — bruk dem direkte):\n"
        + "\n".join(f"- {name}" for name in active) + "\n"
    )


def _build_system_prompt(agent_name: str = "jordan") -> str:
    """Build system prompt: base + active integrations + memory_manager context + smart_memory."""
    base = _load_agent_prompt(agent_name)
    integrations = _active_integrations()

    # Jordan's memory_manager long-term context
    memory_block = ""
    t = _get_tools()
    if t.get("memory_manager"):
        try:
            memory_block = t["memory_manager"].get_context_block()
        except Exception:
            pass

    # NEXUS smart_memory context (keyword-matched, 500-token budget)
    smart_block = ""
    try:
        from memory.smart_memory import get_context
        smart_block = get_context("", max_tokens=400)  # general context at prompt build time
    except Exception:
        pass

    # NEXUS reflection strategy
    strategy_block = ""
    try:
        from agents.reflection_agent import get_current_strategy
        strategy_block = get_current_strategy()
    except Exception:
        pass

    parts = [base, integrations]
    if memory_block:
        parts.append("\n" + memory_block)
    if smart_block:
        parts.append(smart_block)
    if strategy_block:
        parts.append(strategy_block)

    return "".join(parts)


# ── TOOLS list (Anthropic format) ─────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "web_search",
        "description": "Search the web for current information. Returns titles, URLs, and snippets.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query string"}},
            "required": ["query"],
        },
    },
    {
        "name": "scrape_page",
        "description": "Fetch and extract the full text content of a web page.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "The URL to scrape"}},
            "required": ["url"],
        },
    },
    {
        "name": "read_url",
        "description": "Read the content of a URL or link shared by the user. Auto-detects GitHub, Reddit, news, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "max_chars": {"type": "integer", "default": 5000},
            },
            "required": ["url"],
        },
    },
    {
        "name": "browse_web",
        "description": "Use a real browser (Playwright) to interact with JavaScript-heavy pages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to visit"},
                "task": {"type": "string", "description": "What to do: 'read', 'links', 'screenshot', 'search:[query]', 'title'", "default": "read"},
                "selector": {"type": "string", "description": "Optional CSS selector to extract", "default": "body"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "take_screenshot",
        "description": "Take a screenshot of a web page and save it as a PNG.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "output_path": {"type": "string", "default": "outputs/screenshot.png"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "create_website",
        "description": "Create and deploy a website to GitHub Pages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo_name": {"type": "string"},
                "description": {"type": "string"},
                "files": {"type": "object", "description": "Dict of filename → file content"},
            },
            "required": ["repo_name", "description", "files"],
        },
    },
    {
        "name": "propose_email",
        "description": "Propose an email for Nicholas to review and approve before sending. Use ONLY for Nicholas's email (nicholas.elvegaard@gmail.com). For Jarvis's own email use jarvis_send_email.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "follow_up_days": {"type": "integer", "default": 0},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the filesystem.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write or overwrite a file on the filesystem.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "."},
                "recursive": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "run_command",
        "description": "Run a shell command and return stdout/stderr.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "read_emails",
        "description": "Read emails from Nicholas's inbox via IMAP.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 5},
                "unread_only": {"type": "boolean", "default": False},
                "from_address": {"type": "string"},
                "subject_contains": {"type": "string"},
            },
        },
    },
    {
        "name": "check_email_replies",
        "description": "Check if any leads have replied to outreach emails.",
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "default": 3}},
        },
    },
    {
        "name": "update_memory",
        "description": "Update Jordan's long-term memory with a key-value pair.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
                "action": {"type": "string", "enum": ["set", "append", "delete"], "default": "set"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "save_memory",
        "description": "Save something important to NEXUS smart memory for future recall.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "What to remember"},
                "category": {"type": "string", "default": "general"},
                "tags": {"type": "array", "items": {"type": "string"}, "default": []},
                "priority": {"type": "integer", "default": 2, "description": "1=low, 5=critical"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "query_knowledge_base",
        "description": "Search the knowledge base for relevant documents and SOPs.",
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
    {
        "name": "list_calendar_events",
        "description": "List upcoming calendar events.",
        "input_schema": {
            "type": "object",
            "properties": {"days_ahead": {"type": "integer", "default": 7}},
        },
    },
    {
        "name": "create_calendar_event",
        "description": "Create a new calendar event.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "start": {"type": "string", "description": "ISO 8601 datetime"},
                "end": {"type": "string", "description": "ISO 8601 datetime"},
                "description": {"type": "string", "default": ""},
                "location": {"type": "string", "default": ""},
            },
            "required": ["summary", "start", "end"],
        },
    },
    {
        "name": "post_instagram_photo",
        "description": "Post a photo to Instagram.",
        "input_schema": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string"},
                "caption": {"type": "string"},
            },
            "required": ["image_path", "caption"],
        },
    },
    {
        "name": "instagram_dm_inbox",
        "description": "Read Instagram DM conversations.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 10}},
        },
    },
    {
        "name": "instagram_reply_dm",
        "description": "Reply to an Instagram DM conversation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["conversation_id", "message"],
        },
    },
    {
        "name": "instagram_insights",
        "description": "Get Instagram account insights.",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {"type": "string", "default": "impressions,reach,profile_views"},
                "period": {"type": "string", "default": "day"},
            },
        },
    },
    {
        "name": "gmail_read_unread",
        "description": "Read unread Gmail messages.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 10}},
        },
    },
    {
        "name": "gmail_search",
        "description": "Search Gmail inbox.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "gmail_reply",
        "description": "Reply to a Gmail message.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string"},
                "thread_id": {"type": "string"},
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["message_id", "thread_id", "to", "subject", "body"],
        },
    },
    {
        "name": "stripe_balance",
        "description": "Get current Stripe balance.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "stripe_payments",
        "description": "List recent Stripe payments.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 10}},
        },
    },
    {
        "name": "stripe_create_payment_link",
        "description": "Create a Stripe payment link.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount_cents": {"type": "integer"},
                "currency": {"type": "string", "default": "nok"},
                "product_name": {"type": "string"},
            },
            "required": ["amount_cents", "currency", "product_name"],
        },
    },
    {
        "name": "stripe_revenue",
        "description": "Get Stripe revenue for a period.",
        "input_schema": {
            "type": "object",
            "properties": {"months": {"type": "integer", "default": 1}},
        },
    },
    {
        "name": "get_goals",
        "description": "Get current income goal progress (target: 100 000 NOK).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_revenue",
        "description": "Register earned revenue toward the 100 000 NOK goal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount_nok": {"type": "number"},
                "source": {"type": "string"},
                "note": {"type": "string", "default": ""},
            },
            "required": ["amount_nok", "source"],
        },
    },
    {
        "name": "reflect",
        "description": "Run NEXUS self-reflection: analyze recent performance and update strategy.",
        "input_schema": {
            "type": "object",
            "properties": {"force": {"type": "boolean", "default": False}},
        },
    },
    {
        "name": "tiktok_profile",
        "description": "Get TikTok profile info.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "tiktok_videos",
        "description": "List TikTok videos.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 10}},
        },
    },
    {
        "name": "tiktok_upload_video",
        "description": "Upload a video to TikTok.",
        "input_schema": {
            "type": "object",
            "properties": {
                "video_path": {"type": "string"},
                "title": {"type": "string"},
                "privacy": {"type": "string", "default": "SELF_ONLY"},
            },
            "required": ["video_path", "title"],
        },
    },
    {
        "name": "write_notebook",
        "description": "Write a note to Jarvis's notebook.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "category": {"type": "string", "default": "other"},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "read_notebook",
        "description": "Read notes from Jarvis's notebook.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "log_account",
        "description": "Log an account created on a website/platform.",
        "input_schema": {
            "type": "object",
            "properties": {
                "website": {"type": "string"},
                "reason": {"type": "string"},
                "username": {"type": "string"},
                "password": {"type": "string"},
                "email": {"type": "string", "default": "jordan.develepor@outlook.com"},
                "notes": {"type": "string"},
            },
            "required": ["website", "reason", "username", "password"],
        },
    },
    {
        "name": "get_accounts",
        "description": "Get all registered accounts.",
        "input_schema": {
            "type": "object",
            "properties": {"search": {"type": "string"}},
        },
    },
    {
        "name": "ask_gemini",
        "description": "Ask Google Gemini (free, 1M context). Best for long documents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "system": {"type": "string"},
                "model": {"type": "string", "default": "gemini-2.0-flash-exp"},
                "temperature": {"type": "number", "default": 0.7},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "perplexity_search",
        "description": "Deep web research with cited sources via Perplexity AI.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "model": {"type": "string", "default": "sonar-pro"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "log_event",
        "description": "Log an activity event to the shared dashboard.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_type": {"type": "string"},
                "title": {"type": "string"},
                "details": {"type": "string"},
            },
            "required": ["event_type", "title"],
        },
    },
    {
        "name": "jarvis_send_email",
        "description": "Send an email from Jarvis's own address (jordan.develepor@outlook.com). NO approval needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "make_list_scenarios",
        "description": "List Make.com automation scenarios.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "make_trigger_webhook",
        "description": "Trigger a Make.com webhook with a payload.",
        "input_schema": {
            "type": "object",
            "properties": {
                "webhook_url": {"type": "string"},
                "payload": {"type": "object"},
            },
            "required": ["webhook_url", "payload"],
        },
    },
    {
        "name": "teams_post_message",
        "description": "Post a message to a Microsoft Teams channel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_id": {"type": "string"},
                "channel_id": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["team_id", "channel_id", "message"],
        },
    },
    {
        "name": "teams_read_messages",
        "description": "Read recent messages from a Microsoft Teams channel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "team_id": {"type": "string"},
                "channel_id": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["team_id", "channel_id"],
        },
    },
    {
        "name": "delegate",
        "description": "Delegate a task to a specialized sub-agent (sales, research, finance, content, dev, scout, crypto, email, bodo, growth).",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "enum": ["sales", "research", "finance", "content", "dev",
                             "scout", "crypto", "email", "bodo", "growth"],
                },
                "task": {"type": "string"},
            },
            "required": ["agent", "task"],
        },
    },
    {
        "name": "vapi_call",
        "description": "Ring et telefonnummer med Jarvis sin AI-stemme via VAPI. Jarvis snakker direkte med personen. Bruk dette for å ringe Nicholas, kunder, leads eller hvem som helst. Spesifiser gjerne en første setning tilpasset hvem som ringes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to_number": {
                    "type": "string",
                    "description": "Telefonnummer med landkode, f.eks. '+4791349949' eller '+14155552671'",
                },
                "first_message": {
                    "type": "string",
                    "description": "Første setning Jarvis sier når personen tar opp. Tilpass til mottaker.",
                },
            },
            "required": ["to_number"],
        },
    },
    {
        "name": "vapi_call_status",
        "description": "Sjekk status og transkripsjon av en VAPI-samtale.",
        "input_schema": {
            "type": "object",
            "properties": {
                "call_id": {"type": "string", "description": "VAPI call ID fra vapi_call"},
            },
            "required": ["call_id"],
        },
    },
    {
        "name": "read_own_file",
        "description": "Les en av Jarvis sine egne kildefiler på serveren (/opt/nexus/). Bruk for å inspisere og forstå sin egen kode før endringer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relativ path fra /opt/nexus/, f.eks. 'core/engine.py' eller 'agents/jordan/system_prompt.txt'"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_own_file",
        "description": "Skriv eller overskriv en av Jarvis sine egne filer på serveren. Tar automatisk backup. Bruk for å oppdatere system_prompt, tools, eller annen kode.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relativ path fra /opt/nexus/"},
                "content": {"type": "string", "description": "Nytt innhold for filen"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_own_files",
        "description": "List filer og kataloger i Jarvis sin egen kodebase på serveren.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relativ path fra /opt/nexus/, tom streng for rot", "default": ""},
            },
            "required": [],
        },
    },
    {
        "name": "git_commit_and_push",
        "description": "Commit og push endringer i Jarvis sin kodebase til GitHub. Kjør alltid etter write_own_file for å lagre endringer permanent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Commit-melding som beskriver hva som ble endret"},
                "files": {"type": "array", "items": {"type": "string"}, "description": "Spesifikke filer å stage (valgfritt — utelat for å stage alle endringer)"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "run_shell",
        "description": "Kjør en shell-kommando på serveren i /opt/nexus/. Bruk for: git status, pip install, python -c for testing, ls, cat. IKKE bruk for destruktive kommandoer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell-kommando å kjøre"},
                "timeout": {"type": "integer", "description": "Timeout i sekunder (default 30)", "default": 30},
            },
            "required": ["command"],
        },
    },
    {
        "name": "restart_self",
        "description": "Restart Jarvis sin egen service (nexus.service) etter kodeendringer. Jarvis kommer opp igjen om ~5 sekunder. Bruk etter write_own_file + git_commit_and_push.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "google_trends_interest",
        "description": "Se Google Trends interesse over tid for opptil 5 keywords. Finn ut hva folk søker på. Bruk for å finne hot topics, validere ideer, timing for content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Opptil 5 søkeord å sammenligne",
                },
                "timeframe": {
                    "type": "string",
                    "default": "today 3-m",
                    "description": "Tidsperiode: 'today 3-m', 'today 12-m', 'now 7-d', 'now 1-d'",
                },
                "geo": {
                    "type": "string",
                    "default": "",
                    "description": "Landkode: 'NO' for Norge, 'US', '' for hele verden",
                },
            },
            "required": ["keywords"],
        },
    },
    {
        "name": "google_trends_trending",
        "description": "Hent dagens trending searches fra Google Trends for et land.",
        "input_schema": {
            "type": "object",
            "properties": {
                "geo": {
                    "type": "string",
                    "default": "norway",
                    "description": "Land: 'norway', 'united_states', 'united_kingdom'",
                },
            },
        },
    },
    {
        "name": "google_trends_related",
        "description": "Finn relaterte søk (top og rising) for et keyword. Nyttig for SEO og content ideas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string"},
                "geo": {"type": "string", "default": "", "description": "Landkode, tom = hele verden"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "post_tweet",
        "description": "Post en tweet på Twitter/X. Krever TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Tweet-tekst (maks 280 tegn)"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "search_twitter",
        "description": "Søk etter tweets (siste 7 dager). Bruk for å overvåke konkurrenter, trender, leads.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "reddit_search",
        "description": "Søk etter Reddit-poster. Finn leads, trender og diskusjoner.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "subreddit": {"type": "string", "default": "all"},
                "limit": {"type": "integer", "default": 10},
                "sort": {"type": "string", "default": "relevance", "description": "relevance, hot, new, top"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "reddit_hot",
        "description": "Hent hot posts fra en subreddit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subreddit": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["subreddit"],
        },
    },
    {
        "name": "text_to_speech",
        "description": "Generer realistisk tale fra tekst med ElevenLabs. Bruk for podcaster, pitch-videoer, produktdemoer, stemme-produkter til kunder.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Tekst som skal tales"},
                "voice_id": {"type": "string", "description": "ElevenLabs voice ID (valgfritt — bruker Jarvis sin stemme som default)"},
                "model": {"type": "string", "default": "eleven_turbo_v2_5", "description": "eleven_turbo_v2_5 (rask) eller eleven_multilingual_v2 (norsk)"},
                "output_path": {"type": "string", "description": "Filsti for output .mp3"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "gumroad_products",
        "description": "List alle Gumroad-produkter og salg.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "gumroad_sales",
        "description": "Hent salgstall fra Gumroad.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Filtrer på spesifikt produkt (valgfritt)"},
            },
        },
    },
    {
        "name": "gumroad_create_product",
        "description": "Opprett et nytt digitalt produkt på Gumroad og start å selge det.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "price_cents": {"type": "integer", "description": "Pris i øre/cents, f.eks. 4900 = 49 USD"},
                "description": {"type": "string"},
                "url": {"type": "string", "description": "Produktets unique URL slug"},
            },
            "required": ["name", "price_cents"],
        },
    },
    {
        "name": "vercel_projects",
        "description": "List alle Vercel-prosjekter og status.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "vercel_deploy",
        "description": "Trigger en ny deployment av et Vercel-prosjekt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Vercel project name eller ID"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "generate_image",
        "description": "Generer et bilde med DALL-E 3. Bruk for produktbilder, thumbnails, markedsføring.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Bildebeskrivelse på engelsk"},
                "size": {"type": "string", "default": "1024x1024", "description": "1024x1024, 1024x1792 (portrett), 1792x1024 (landskap)"},
                "quality": {"type": "string", "default": "standard", "description": "standard eller hd"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "apollo_search_leads",
        "description": "Søk etter leads (beslutningstakere) i Apollo.io. Finn CEOs, founders og daglige ledere i norske selskaper.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_titles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Stillingstitler, f.eks. ['CEO', 'Daglig leder', 'Founder']",
                    "default": ["CEO", "Daglig leder", "Founder"],
                },
                "countries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["Norway"],
                },
                "min_employees": {"type": "integer", "default": 5},
                "max_employees": {"type": "integer", "default": 500},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "apollo_search_companies",
        "description": "Søk etter selskaper i Apollo.io.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keywords": {"type": "array", "items": {"type": "string"}},
                "countries": {"type": "array", "items": {"type": "string"}, "default": ["Norway"]},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "get_news",
        "description": "Hent nyheter fra NRK, E24, DN, TechCrunch og Hacker News. Bruk for daglig oppdatering og market intelligence.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit_per_source": {"type": "integer", "default": 3},
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filtrer kilder: NRK, E24, DN, TechCrunch, HN. Tom = alle.",
                    "default": [],
                },
            },
        },
    },
    {
        "name": "crypto_prices",
        "description": "Hent kryptovaluta-priser og markedsdata fra CoinGecko (gratis, ingen API-key).",
        "input_schema": {
            "type": "object",
            "properties": {
                "coins": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "CoinGecko coin IDs, f.eks. ['bitcoin', 'solana', 'ethereum']",
                    "default": ["bitcoin", "solana", "ethereum"],
                },
                "currency": {"type": "string", "default": "nok", "description": "nok, usd, eur"},
            },
        },
    },
    # ── MiniMax ──────────────────────────────────────────────────────────────
    # ── Brønnøysund ──────────────────────────────────────────────────────────
    {
        "name": "brreg_find_leads",
        "description": "Finn norske AS fra Brønnøysundregistrene — gratis, ingen API-key. Bruk til å finne leads i Norge etter bransje og størrelse. Vanlige NACE-koder: 62=IT, 41=Bygg, 47=Handel, 70=Konsulent, 86=Helse.",
        "input_schema": {
            "type": "object",
            "properties": {
                "industry_code": {"type": "string", "description": "NACE-kode, f.eks. '62' for IT", "default": "62"},
                "min_employees": {"type": "integer", "description": "Minimum ansatte", "default": 5},
                "max_employees": {"type": "integer", "description": "Maksimum ansatte", "default": 50},
                "municipality": {"type": "string", "description": "Kommunenavn, f.eks. OSLO, BODØ, BERGEN"},
                "max_results": {"type": "integer", "description": "Maks antall resultater", "default": 20},
            },
        },
    },
    {
        "name": "brreg_get_company",
        "description": "Hent full info om én norsk bedrift via org.nummer fra Brønnøysundregistrene.",
        "input_schema": {
            "type": "object",
            "properties": {
                "org_number": {"type": "string", "description": "9-sifret org.nummer"},
            },
            "required": ["org_number"],
        },
    },
    {
        "name": "github_list_repos",
        "description": "List alle GitHub-repos under nicholaselvegaard-commits. Bruk alltid FOR du sper om repo-navn.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "github_push_file",
        "description": "Push en fil til GitHub-repo. Oppretter eller oppdaterer filen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repo-navn uten owner"},
                "path": {"type": "string", "description": "Filsti i repo"},
                "content": {"type": "string", "description": "Filinnhold"},
                "message": {"type": "string", "description": "Commit-melding"},
                "branch": {"type": "string", "default": "main"},
            },
            "required": ["repo", "path", "content", "message"],
        },
    },
    {
        "name": "github_create_repo",
        "description": "Opprett nytt GitHub-repo under nicholaselvegaard-commits.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string", "default": ""},
                "private": {"type": "boolean", "default": False},
            },
            "required": ["name"],
        },
    },
    {
        "name": "stripe_create_link",
        "description": "Opprett Stripe payment link. Bruk for a selge produkter/tjenester til kunder direkte.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {"type": "string"},
                "amount_nok": {"type": "integer"},
                "description": {"type": "string", "default": ""},
            },
            "required": ["product_name", "amount_nok"],
        },
    },
    {
        "name": "minimax_chat",
        "description": "Chat med MiniMax LLM (M2.5-highspeed rask/billig, M2.7 kraftig). Bruk for kodeoppgaver, analyse, innhold — billigere enn Claude for rutineoppgaver.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Meldingen til modellen"},
                "system": {"type": "string", "description": "System-prompt (valgfri)"},
                "model": {
                    "type": "string",
                    "description": "MiniMax-M2.5-highspeed | MiniMax-M2.5 | MiniMax-M2.7 | MiniMax-M2.7-highspeed",
                    "default": "MiniMax-M2.5-highspeed",
                },
                "max_tokens": {"type": "integer", "default": 1000},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "minimax_tts",
        "description": "Generer realistisk tale fra tekst med MiniMax. 40 språk, 7 emosjoner. Alternativ til ElevenLabs — bruk for podcaster, produktdemoer, pitch-videoer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Tekst å syntetisere (maks 10 000 tegn)"},
                "voice_id": {
                    "type": "string",
                    "description": "Stemme: Insightful_Speaker | Graceful_Lady | Lucky_Robot",
                    "default": "Insightful_Speaker",
                },
                "model": {
                    "type": "string",
                    "description": "speech-2.8-turbo (rask) | speech-2.8-hd (høy kvalitet)",
                    "default": "speech-2.8-turbo",
                },
                "emotion": {
                    "type": "string",
                    "description": "neutral | happy | sad | angry | fear | surprise | disgust",
                    "default": "neutral",
                },
                "language_boost": {
                    "type": "string",
                    "description": "auto | en-US | no | zh-CN",
                    "default": "auto",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "minimax_video",
        "description": "Generer video fra tekst (eller bilde) med MiniMax Hailuo 2.3. Opp til 1080p, 6-10 sekunder. Bruk for markedsføring, produktdemoer, innhold.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Beskrivelse av videoen. Støtter kamerabevegelser: [Pan left], [Zoom in], [Tracking shot]"},
                "resolution": {"type": "string", "description": "720P | 1080P", "default": "1080P"},
                "duration": {"type": "integer", "description": "6 eller 10 sekunder", "default": 6},
                "image_url": {"type": "string", "description": "URL til startbilde for image-to-video (valgfri)"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "minimax_music",
        "description": "Generer original musikk fra tekst og lyrics med MiniMax. Alle sjangre. Bruk for innhold, produkter, bakgrunnsmusikk.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Beskriv stil og stemning, f.eks. 'upbeat lo-fi hip-hop for studying'"},
                "lyrics": {"type": "string", "description": "Sangtekst med [Verse], [Chorus] etc. Utelat for auto-genererte lyrics eller instrumental."},
                "instrumental": {"type": "boolean", "description": "True = kun instrumentalmusikk uten vokal", "default": False},
            },
            "required": ["prompt"],
        },
    },
]


# ── History helpers ───────────────────────────────────────────────────────────

def _serialize_content(content) -> list[dict]:
    result = []
    for block in content:
        if isinstance(block, dict):
            result.append(block)
        elif hasattr(block, "model_dump"):
            result.append(block.model_dump())
        else:
            result.append({"type": "text", "text": str(block)})
    return result


def _load_pending_actions() -> dict:
    if PENDING_ACTIONS_FILE.exists():
        try:
            return json.loads(PENDING_ACTIONS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


def _save_pending_actions(actions: dict) -> None:
    PENDING_ACTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_ACTIONS_FILE.write_text(
        json.dumps(actions, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _sanitize_history(messages: list[dict]) -> list[dict]:
    """Strip broken tool_use / tool_result pairs from history."""
    clean = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            if any(
                isinstance(b, dict) and b.get("type") in ("tool_use", "tool_result")
                for b in content
            ):
                continue
        clean.append(msg)
    return clean


def _trim_for_api(messages: list[dict]) -> list[dict]:
    if len(messages) <= MAX_API_HISTORY:
        return messages
    older = messages[:-MAX_API_HISTORY]
    t = _get_tools()
    if t.get("memory_manager"):
        summary_parts = []
        for m in older:
            c = m.get("content", "")
            if isinstance(c, str) and c.strip():
                summary_parts.append(f"[{m['role']}] {c[:120]}")
        if summary_parts:
            try:
                compressed = "[history compressed] " + " | ".join(summary_parts[:5])
                t["memory_manager"].add_conversation_summary(compressed)
            except Exception:
                pass
    return messages[-MAX_API_HISTORY:]


def _load_history(chat_id: str) -> list[dict]:
    path = CONVERSATIONS_DIR / f"{chat_id}.json"
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return _sanitize_history(raw)
        except (json.JSONDecodeError, ValueError):
            pass
    return []


def _save_history(chat_id: str, messages: list[dict]) -> None:
    path = CONVERSATIONS_DIR / f"{chat_id}.json"
    path.write_text(
        json.dumps(messages[-40:], indent=2, ensure_ascii=False), encoding="utf-8"
    )


def clear_history(chat_id: str) -> None:
    path = CONVERSATIONS_DIR / f"{chat_id}.json"
    if path.exists():
        path.unlink()


# ── Tool execution ────────────────────────────────────────────────────────────

async def _execute_tool(
    name: str,
    inputs: dict,
    chat_id: str,
    telegram_send: TelegramSendFn,
) -> str:
    t = _get_tools()
    try:
        if name == "web_search":
            if not t.get("web_search"):
                return "web_search tool not available."
            results = t["web_search"].search(inputs["query"])
            if not results:
                return "No results found."
            return "\n".join(f"- [{r.title}]({r.url})\n  {r.snippet}" for r in results)

        elif name == "scrape_page":
            if not t.get("scraper"):
                return "scraper not available."
            page = t["scraper"].scrape(inputs["url"])
            return f"Title: {page.title}\n\n{page.text[:6000]}"

        elif name == "read_url":
            url = inputs["url"]
            max_chars = inputs.get("max_chars", 5000)
            if t.get("url_reader"):
                try:
                    return t["url_reader"].read_url(url, max_chars=max_chars)
                except Exception:
                    pass
            if t.get("scraper"):
                page = t["scraper"].scrape(url)
                return f"Title: {page.title}\n\n{page.text[:max_chars]}"
            return "URL reading not available."

        elif name == "browse_web":
            if not t.get("browser"):
                return "Browser tool not available."
            try:
                from tools.browser import browse
                result = await browse(
                    url=inputs["url"],
                    task=inputs.get("task", "read"),
                    selector=inputs.get("selector", "body"),
                )
                return result
            except Exception as e:
                return f"Browser failed: {e}"

        elif name == "take_screenshot":
            if not t.get("browser"):
                return "Browser tool not available."
            path = await t["browser"].take_screenshot(
                url=inputs["url"],
                output_path=inputs.get("output_path", "outputs/screenshot.png"),
            )
            return f"Screenshot saved to: {path}"

        elif name == "create_website":
            if not t.get("github"):
                return "GitHub tool not available."
            url = t["github"].deploy_to_pages(
                repo_name=inputs["repo_name"],
                description=inputs["description"],
                files=inputs["files"],
            )
            return f"Website deployed. URL: {url}"

        elif name == "propose_email":
            action_id = str(uuid.uuid4())[:8]
            actions = _load_pending_actions()
            actions[action_id] = {
                "type": "email",
                "status": "pending",
                "to": inputs["to"],
                "subject": inputs["subject"],
                "body": inputs["body"],
                "follow_up_days": inputs.get("follow_up_days", 0),
                "chat_id": chat_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "sent_at": None,
                "follow_up_sent": False,
            }
            _save_pending_actions(actions)
            preview = (
                f"📧 *Forslag til e-post* — ID: `{action_id}`\n\n"
                f"*Til:* {inputs['to']}\n"
                f"*Emne:* {inputs['subject']}\n\n"
                f"```\n{inputs['body']}\n```\n\n"
            )
            reply_markup = {
                "inline_keyboard": [[
                    {"text": "✅ Send", "callback_data": f"send_email:{action_id}"},
                    {"text": "❌ Avbryt", "callback_data": f"cancel_email:{action_id}"},
                ]]
            }
            await telegram_send(chat_id, preview, reply_markup)
            return f"Email draft (ID: {action_id}) sent to Telegram for approval."

        elif name == "read_file":
            if not t.get("file_manager"):
                return (BASE_DIR / inputs["path"]).read_text(encoding="utf-8", errors="ignore")[:8000]
            return t["file_manager"].read_file(inputs["path"])[:8000]

        elif name == "write_file":
            if t.get("file_manager"):
                t["file_manager"].write_file(inputs["path"], inputs["content"], backup=False)
            else:
                p = Path(inputs["path"])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(inputs["content"], encoding="utf-8")
            return f"File written: {inputs['path']}"

        elif name == "list_files":
            base = inputs.get("path", ".")
            if inputs.get("recursive", False):
                result = []
                for root, dirs, files in os.walk(base):
                    dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git", "node_modules", ".venv", "venv"]]
                    for f in files:
                        result.append(os.path.join(root, f).replace("\\", "/"))
                return "\n".join(result[:200])
            else:
                entries = os.listdir(base) if os.path.isdir(base) else []
                lines = [f + ("/" if os.path.isdir(os.path.join(base, f)) else "") for f in sorted(entries)]
                return "\n".join(lines)

        elif name == "run_command":
            if not t.get("shell"):
                import subprocess
                r = subprocess.run(inputs["command"], shell=True, capture_output=True, text=True, timeout=30)
                return f"Exit code: {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"[:4000]
            result = t["shell"].run(inputs["command"])
            return f"Exit code: {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"[:4000]

        elif name == "read_emails":
            if not t.get("email_reader"):
                return "Email reader not configured."
            emails = t["email_reader"].fetch_emails(
                limit=inputs.get("limit", 5),
                unread_only=inputs.get("unread_only", False),
                from_address=inputs.get("from_address"),
                subject_contains=inputs.get("subject_contains"),
            )
            if not emails:
                return "No emails found."
            return "\n\n".join(
                f"---\nFra: {e.sender}\nEmne: {e.subject}\nDato: {e.date}\n\n{e.body}"
                for e in emails
            )

        elif name == "check_email_replies":
            try:
                from tools.email_reader import format_replies_for_nexus
                return format_replies_for_nexus(days=inputs.get("days", 3))
            except Exception as e:
                return f"Kunne ikke sjekke e-postsvar: {e}"

        elif name == "update_memory":
            if not t.get("memory_manager"):
                return "Memory manager not available."
            return t["memory_manager"].update_memory(
                key=inputs["key"],
                value=inputs["value"],
                action=inputs.get("action", "set"),
            )

        elif name == "save_memory":
            try:
                from memory.smart_memory import save
                save(
                    category=inputs.get("category", "general"),
                    content=inputs["content"],
                    tags=inputs.get("tags", []),
                    priority=inputs.get("priority", 2),
                )
                return f"Saved to smart memory: {inputs['content'][:80]}"
            except Exception as e:
                return f"Memory save failed: {e}"

        elif name == "query_knowledge_base":
            try:
                from memory.knowledge_base import query
                return query(inputs["question"]) or "Fant ingenting i kunnskapsbasen."
            except Exception as e:
                return f"Knowledge base query failed: {e}"

        elif name == "list_calendar_events":
            if not t.get("calendar"):
                return "Calendar not configured."
            events = t["calendar"].list_events(days_ahead=inputs.get("days_ahead", 7))
            if not events:
                return "No upcoming events."
            return "\n".join(
                f"- **{e['summary']}** Start: {e['start']} | Slutt: {e['end']}"
                for e in events
            )

        elif name == "create_calendar_event":
            if not t.get("calendar"):
                return "Calendar not configured."
            event = t["calendar"].create_event(
                summary=inputs["summary"],
                start=inputs["start"],
                end=inputs["end"],
                description=inputs.get("description", ""),
                location=inputs.get("location", ""),
            )
            return f"Event created: {event['summary']}\nLink: {event.get('htmlLink', '')}"

        elif name == "post_instagram_photo":
            if not t.get("instagram"):
                return "Instagram not configured."
            result = t["instagram"].post_photo(image_path=inputs["image_path"], caption=inputs["caption"])
            return f"Instagram photo posted! URL: {result['url']}"

        elif name == "instagram_dm_inbox":
            if not t.get("instagram"):
                return "Instagram not configured."
            convs = t["instagram"].read_dm_inbox(limit=inputs.get("limit", 10))
            if not convs:
                return "No DM conversations found."
            return "\n".join(
                f"- [{c['id']}] {', '.join(c['participants'])} — \"{c['snippet']}\""
                for c in convs
            )

        elif name == "instagram_reply_dm":
            if not t.get("instagram"):
                return "Instagram not configured."
            result = t["instagram"].reply_to_dm(
                conversation_id=inputs["conversation_id"],
                message=inputs["message"],
            )
            return f"DM reply sent. ID: {result['message_id']}"

        elif name == "instagram_insights":
            if not t.get("instagram"):
                return "Instagram not configured."
            insights = t["instagram"].get_insights(
                metric=inputs.get("metric", "impressions,reach,profile_views"),
                period=inputs.get("period", "day"),
            )
            if not insights:
                return "No insights data."
            return "\n".join(
                f"- {i.get('title', i['name'])}: {i['values'][-1]['value'] if i.get('values') else 'N/A'}"
                for i in insights
            )

        elif name == "gmail_read_unread":
            if not t.get("gmail"):
                return "Gmail not configured."
            emails = t["gmail"].read_unread(limit=inputs.get("limit", 10))
            if not emails:
                return "No unread emails."
            return "\n\n".join(
                f"---\nID: {e.id}\nFra: {e.sender}\nEmne: {e.subject}\n\n{e.body}"
                for e in emails
            )

        elif name == "gmail_search":
            if not t.get("gmail"):
                return "Gmail not configured."
            emails = t["gmail"].search_inbox(query=inputs["query"], limit=inputs.get("limit", 10))
            if not emails:
                return "No emails found."
            return "\n\n".join(
                f"---\nID: {e.id}\nFra: {e.sender}\nEmne: {e.subject}\n\n{e.body}"
                for e in emails
            )

        elif name == "gmail_reply":
            if not t.get("gmail"):
                return "Gmail not configured."
            sent_id = t["gmail"].reply_to_email(
                message_id=inputs["message_id"],
                thread_id=inputs["thread_id"],
                to=inputs["to"],
                subject=inputs["subject"],
                body=inputs["body"],
            )
            return f"Gmail reply sent. ID: {sent_id}"

        elif name == "stripe_balance":
            if not t.get("stripe"):
                return "Stripe not configured."
            balance = t["stripe"].get_balance()
            avail = ", ".join(f"{v} {k}" for k, v in balance["available"].items()) or "0"
            pend  = ", ".join(f"{v} {k}" for k, v in balance["pending"].items()) or "0"
            return f"Stripe balance:\n- Tilgjengelig: {avail}\n- Pending: {pend}"

        elif name == "stripe_payments":
            if not t.get("stripe"):
                return "Stripe not configured."
            payments = t["stripe"].list_payments(limit=inputs.get("limit", 10))
            if not payments:
                return "No payments found."
            return "\n".join(
                f"- {p['amount']} {p['currency']} | {p['status']} | {p.get('description', '')} | ID: {p['id']}"
                for p in payments
            )

        elif name == "stripe_create_payment_link":
            if not t.get("stripe"):
                return "Stripe not configured."
            result = t["stripe"].create_payment_link(
                amount_cents=inputs["amount_cents"],
                currency=inputs["currency"],
                product_name=inputs["product_name"],
            )
            return f"Payment link: {result['url']}"

        elif name == "stripe_revenue":
            if not t.get("stripe"):
                return "Stripe not configured."
            rev = t["stripe"].get_revenue(months=inputs.get("months", 1))
            if not rev["revenue_by_currency"]:
                return "No revenue recorded."
            amounts = ", ".join(f"{v} {k}" for k, v in rev["revenue_by_currency"].items())
            return f"Revenue: {amounts} ({rev['payment_count']} betalinger)"

        elif name == "get_goals":
            try:
                from memory.goals import format_for_telegram
                return format_for_telegram()
            except Exception as e:
                return f"Kunne ikke hente mål: {e}"

        elif name == "add_revenue":
            try:
                from memory.goals import add_revenue
                return add_revenue(
                    amount_nok=inputs["amount_nok"],
                    source=inputs["source"],
                    note=inputs.get("note", ""),
                )
            except Exception as e:
                return f"Kunne ikke registrere inntekt: {e}"

        elif name == "reflect":
            try:
                from agents.reflection_agent import reflect_sync
                return reflect_sync()
            except Exception as e:
                return f"Refleksjon feilet: {e}"

        elif name == "tiktok_profile":
            if not t.get("tiktok"):
                return "TikTok not configured."
            info = t["tiktok"].get_user_info()
            return (
                f"TikTok: @{info.get('display_name')}\n"
                f"Followers: {info.get('follower_count', 0):,}\n"
                f"Likes: {info.get('likes_count', 0):,}"
            )

        elif name == "tiktok_videos":
            if not t.get("tiktok"):
                return "TikTok not configured."
            videos = t["tiktok"].list_videos(limit=inputs.get("limit", 10))
            if not videos:
                return "No TikTok videos found."
            return "\n".join(
                f"- {v.get('title', '(ingen tittel)')} | Views: {v.get('view_count', 0):,}"
                for v in videos
            )

        elif name == "tiktok_upload_video":
            if not t.get("tiktok"):
                return "TikTok not configured."
            result = t["tiktok"].upload_video(
                video_path=inputs["video_path"],
                title=inputs["title"],
                privacy=inputs.get("privacy", "SELF_ONLY"),
            )
            return f"TikTok upload started. Publish ID: {result['publish_id']}"

        elif name == "write_notebook":
            if not t.get("notebook"):
                return "Notebook not available."
            result = t["notebook"].write_note(
                title=inputs["title"],
                content=inputs["content"],
                category=inputs.get("category", "other"),
            )
            return f"Note saved #{result['id']} — {inputs['title']}"

        elif name == "read_notebook":
            if not t.get("notebook"):
                return "Notebook not available."
            entries = t["notebook"].read_notes(
                category=inputs.get("category"),
                limit=inputs.get("limit", 20),
            )
            if not entries:
                return "Notatboken er tom."
            return "\n\n".join(
                f"#{e['id']} [{e['category']}] {e['timestamp'][:10]}\n{e['title']}: {e['content']}"
                for e in entries
            )

        elif name == "log_account":
            if not t.get("account_registry"):
                return "Account registry not available."
            t["account_registry"].log_account(
                website=inputs["website"],
                reason=inputs["reason"],
                username=inputs["username"],
                password=inputs["password"],
                email=inputs.get("email", "jordan.develepor@outlook.com"),
                notes=inputs.get("notes", ""),
            )
            return f"Account logged: {inputs['website']}"

        elif name == "get_accounts":
            if not t.get("account_registry"):
                return "Account registry not available."
            accounts = t["account_registry"].get_accounts(search=inputs.get("search"))
            if not accounts:
                return "Ingen kontoer registrert."
            return "\n\n".join(
                f"🌐 {a['website']}\n   Email: {a['email']}\n   Bruker: {a['username']} | Pass: {a['password']}"
                for a in accounts
            )

        elif name == "ask_gemini":
            if not t.get("gemini"):
                return "Gemini not configured."
            return t["gemini"].ask(
                prompt=inputs["prompt"],
                system=inputs.get("system"),
                model=inputs.get("model", "gemini-2.0-flash-exp"),
                temperature=inputs.get("temperature", 0.7),
            )

        elif name == "perplexity_search":
            if not t.get("perplexity"):
                return "Perplexity not configured."
            result = t["perplexity"].search(
                query=inputs["query"],
                model=inputs.get("model", "sonar-pro"),
            )
            answer = result["answer"]
            citations = result.get("citations", [])
            if citations:
                answer += "\n\nKilder:\n" + "\n".join(f"- {c}" for c in citations[:5])
            return answer

        elif name == "log_event":
            if t.get("supabase"):
                try:
                    t["supabase"].log_event(
                        agent_name="jarvis",
                        event_type=inputs["event_type"],
                        title=inputs["title"],
                        details=inputs.get("details", ""),
                    )
                except Exception:
                    pass
            return f"Event logged: [{inputs['event_type']}] {inputs['title']}"

        elif name == "jarvis_send_email":
            if not t.get("jarvis_email"):
                return "Jarvis email not configured."
            t["jarvis_email"].send_email(
                to=inputs["to"],
                subject=inputs["subject"],
                body=inputs["body"],
            )
            return f"✅ Email sent from jordan.develepor@outlook.com → {inputs['to']}"

        elif name == "make_list_scenarios":
            if not t.get("make"):
                return "Make.com not configured."
            scenarios = t["make"].list_scenarios()
            if not scenarios:
                return "Ingen Make.com scenarios funnet."
            return "\n".join(f"- #{s.get('id')} {s.get('name')}" for s in scenarios)

        elif name == "make_trigger_webhook":
            if not t.get("make"):
                return "Make.com not configured."
            t["make"].trigger_webhook(
                webhook_url=inputs["webhook_url"],
                payload=inputs.get("payload", {}),
            )
            return f"Make.com webhook trigget: {inputs['webhook_url'][:60]}"

        elif name == "teams_post_message":
            if not t.get("teams"):
                return "Teams not configured."
            result = t["teams"].post_to_channel(
                team_id=inputs["team_id"],
                channel_id=inputs["channel_id"],
                message=inputs["message"],
            )
            return f"Teams message posted. ID: {result['id']}"

        elif name == "teams_read_messages":
            if not t.get("teams"):
                return "Teams not configured."
            messages = t["teams"].read_channel_messages(
                team_id=inputs["team_id"],
                channel_id=inputs["channel_id"],
                limit=inputs.get("limit", 10),
            )
            if not messages:
                return "No messages found."
            return "\n".join(f"[{m['createdDateTime']}] {m['sender']}: {m['body']}" for m in messages)

        elif name == "delegate":
            try:
                from tools.delegate import delegate
                return await delegate(agent=inputs["agent"], task=inputs["task"])
            except Exception as e:
                return f"Delegate failed: {e}"

        elif name == "vapi_call":
            try:
                from tools.vapi_call import make_call
                result = make_call(
                    to_number=inputs["to_number"],
                    first_message=inputs.get("first_message"),
                )
                if result.get("success"):
                    return f"✅ Ringer {inputs['to_number']} — call_id: {result['call_id']}"
                return f"❌ Kunne ikke ringe: {result.get('error')}"
            except Exception as e:
                return f"vapi_call failed: {e}"

        elif name == "vapi_call_status":
            try:
                from tools.vapi_call import get_call_status
                return str(get_call_status(inputs["call_id"]))
            except Exception as e:
                return f"vapi_call_status failed: {e}"

        elif name == "read_own_file":
            try:
                from tools.self_modify import read_own_file
                return read_own_file(inputs["path"])
            except Exception as e:
                return f"read_own_file failed: {e}"

        elif name == "write_own_file":
            try:
                from tools.self_modify import write_own_file
                return write_own_file(inputs["path"], inputs["content"])
            except Exception as e:
                return f"write_own_file failed: {e}"

        elif name == "list_own_files":
            try:
                from tools.self_modify import list_own_files
                return list_own_files(inputs.get("path", ""))
            except Exception as e:
                return f"list_own_files failed: {e}"

        elif name == "git_commit_and_push":
            try:
                from tools.self_modify import git_commit_and_push
                return git_commit_and_push(inputs["message"], inputs.get("files"))
            except Exception as e:
                return f"git_commit failed: {e}"

        elif name == "run_shell":
            try:
                from tools.self_modify import run_shell
                return run_shell(inputs["command"], inputs.get("timeout", 30))
            except Exception as e:
                return f"run_shell failed: {e}"

        elif name == "restart_self":
            try:
                from tools.self_modify import restart_self
                return restart_self()
            except Exception as e:
                return f"restart_self failed: {e}"

        elif name == "google_trends_interest":
            if not t.get("google_trends"):
                return "Google Trends not available (pip install pytrends)."
            data = t["google_trends"].get_interest_over_time(
                keywords=inputs["keywords"],
                timeframe=inputs.get("timeframe", "today 3-m"),
                geo=inputs.get("geo", ""),
            )
            if "error" in data:
                return f"Google Trends error: {data['error']}"
            lines = []
            for kw, points in data.items():
                if points:
                    last = points[-1]
                    trend = "↑" if len(points) > 1 and points[-1][1] > points[-2][1] else "↓"
                    lines.append(f"**{kw}**: {last[1]}/100 {trend} (siste: {last[0]})")
                    lines.append("  " + " → ".join(f"{v}" for _, v in points[-5:]))
            return "\n".join(lines) if lines else "Ingen trenddata funnet."

        elif name == "google_trends_trending":
            if not t.get("google_trends"):
                return "Google Trends not available."
            geo = inputs.get("geo", "norway")
            trends = t["google_trends"].get_trending_searches(geo=geo)
            if not trends or (len(trends) == 1 and "Error" in str(trends[0])):
                return f"Kunne ikke hente trending: {trends}"
            return f"Trending i {geo}:\n" + "\n".join(f"{i+1}. {t_}" for i, t_ in enumerate(trends[:15]))

        elif name == "google_trends_related":
            if not t.get("google_trends"):
                return "Google Trends not available."
            data = t["google_trends"].get_related_queries(
                keyword=inputs["keyword"],
                geo=inputs.get("geo", ""),
            )
            if "error" in data:
                return f"Google Trends error: {data['error']}"
            lines = [f"Relaterte søk for '{inputs['keyword']}':"]
            if data.get("top"):
                lines.append("Top: " + ", ".join(data["top"][:8]))
            if data.get("rising"):
                lines.append("Rising: " + ", ".join(data["rising"][:8]))
            return "\n".join(lines)

        elif name == "post_tweet":
            if not t.get("twitter"):
                return "Twitter not configured."
            result = t["twitter"].post_tweet(text=inputs["text"])
            return f"Tweet postet! ID: {result.get('id')}"

        elif name == "search_twitter":
            if not t.get("twitter"):
                return "Twitter not configured."
            tweets = t["twitter"].search_recent(query=inputs["query"], limit=inputs.get("limit", 10))
            if not tweets:
                return "Ingen tweets funnet."
            return "\n".join(f"- {tw.get('text', '')[:120]}" for tw in tweets[:10])

        elif name == "reddit_search":
            if not t.get("reddit"):
                return "Reddit not configured (REDDIT_CLIENT_ID/SECRET needed)."
            posts = t["reddit"].search(
                query=inputs["query"],
                subreddit=inputs.get("subreddit", "all"),
                limit=inputs.get("limit", 10),
                sort=inputs.get("sort", "relevance"),
            )
            if not posts:
                return "Ingen Reddit-poster funnet."
            return "\n".join(
                f"- [{p.subreddit}] {p.title} (↑{p.score}) {p.url}"
                for p in posts[:10]
            )

        elif name == "reddit_hot":
            if not t.get("reddit"):
                return "Reddit not configured."
            posts = t["reddit"].get_hot(
                subreddit=inputs["subreddit"],
                limit=inputs.get("limit", 10),
            )
            if not posts:
                return "Ingen hot posts funnet."
            return "\n".join(
                f"- {p.title} (↑{p.score}, {p.num_comments} komm.) {p.url}"
                for p in posts[:10]
            )

        elif name == "text_to_speech":
            if not t.get("elevenlabs"):
                return "ElevenLabs not configured (ELEVENLABS_API_KEY missing)."
            path = t["elevenlabs"].text_to_speech(
                text=inputs["text"],
                voice_id=inputs.get("voice_id"),
                model=inputs.get("model", "eleven_turbo_v2_5"),
                output_path=inputs.get("output_path"),
            )
            return f"Audio generated: {path}"

        elif name == "gumroad_products":
            if not t.get("gumroad"):
                return "Gumroad not configured (GUMROAD_ACCESS_TOKEN missing)."
            products = t["gumroad"].list_products()
            if not products:
                return "Ingen Gumroad-produkter funnet."
            return "\n".join(
                f"- {p.get('name')} | ${p.get('price', 0)/100:.2f} | {p.get('sales_count', 0)} salg"
                for p in products
            )

        elif name == "gumroad_sales":
            if not t.get("gumroad"):
                return "Gumroad not configured."
            sales = t["gumroad"].get_sales(product_id=inputs.get("product_id"))
            if not sales:
                return "Ingen Gumroad-salg funnet."
            total = sum(float(s.get("price", 0)) for s in sales)
            return f"{len(sales)} salg totalt, ${total:.2f}\n" + "\n".join(
                f"- {s.get('created_at', '')[:10]} | {s.get('email', '')} | ${s.get('price', 0)}"
                for s in sales[:10]
            )

        elif name == "gumroad_create_product":
            if not t.get("gumroad"):
                return "Gumroad not configured."
            result = t["gumroad"].create_product(
                name=inputs["name"],
                price_cents=inputs["price_cents"],
                description=inputs.get("description", ""),
                url=inputs.get("url"),
            )
            short_url = result.get("short_url") or result.get("url", "")
            return f"Produkt opprettet: {result.get('name')} | URL: {short_url}"

        elif name == "vercel_projects":
            if not t.get("vercel"):
                return "Vercel not configured (VERCEL_TOKEN missing)."
            projects = t["vercel"].list_projects()
            if not projects:
                return "Ingen Vercel-prosjekter funnet."
            return "\n".join(
                f"- {p.get('name')} | {p.get('framework', 'N/A')} | {p.get('updatedAt', '')[:10]}"
                for p in projects[:15]
            )

        elif name == "vercel_deploy":
            if not t.get("vercel"):
                return "Vercel not configured."
            result = t["vercel"].trigger_deploy(project_id=inputs["project_id"])
            url = result.get("url", "")
            state = result.get("readyState", result.get("state", "deploying"))
            return f"Deploy startet: {url} | Status: {state}"

        elif name == "generate_image":
            if not t.get("image_gen"):
                return "Image generation unavailable. Check HUGGINGFACE_API_KEY in .env."
            path = t["image_gen"].generate_image(
                prompt=inputs["prompt"],
                size=inputs.get("size", "1024x1024"),
                quality=inputs.get("quality", "standard"),
            )
            return f"Bilde generert: {path}"

        elif name == "apollo_search_leads":
            if not t.get("apollo"):
                return "Apollo not configured (APOLLO_API_KEY missing)."
            leads = t["apollo"].search_people(
                job_titles=inputs.get("job_titles", ["CEO", "Daglig leder", "Founder"]),
                countries=inputs.get("countries", ["Norway"]),
                min_employees=inputs.get("min_employees", 5),
                max_employees=inputs.get("max_employees", 500),
                per_page=min(inputs.get("limit", 20), 50),
            )
            if not leads:
                return "Ingen leads funnet."
            return f"{len(leads)} leads funnet:\n" + "\n".join(
                f"- {l.get('name', '')} | {l.get('title', '')} | {l.get('company', '')} | {l.get('email', 'no email')}"
                for l in leads[:15]
            )

        elif name == "apollo_search_companies":
            if not t.get("apollo"):
                return "Apollo not configured."
            companies = t["apollo"].search_companies(
                keywords=inputs.get("keywords", []),
                countries=inputs.get("countries", ["Norway"]),
                per_page=min(inputs.get("limit", 20), 50),
            )
            if not companies:
                return "Ingen selskaper funnet."
            return f"{len(companies)} selskaper:\n" + "\n".join(
                f"- {c.get('name', '')} | {c.get('industry', '')} | {c.get('num_employees', '')} ansatte | {c.get('website', '')}"
                for c in companies[:15]
            )

        elif name == "get_news":
            if not t.get("news_fetcher"):
                return "News fetcher not available."
            sources_filter = inputs.get("sources", [])
            limit = inputs.get("limit_per_source", 3)
            if sources_filter:
                items = []
                for src in sources_filter:
                    url = t["news_fetcher"].RSS_FEEDS.get(src)
                    if url:
                        items.extend(t["news_fetcher"].fetch_rss(url, src, limit))
            else:
                items = t["news_fetcher"].fetch_all(limit_per_source=limit)
            if not items:
                return "Ingen nyheter funnet."
            return "\n".join(
                f"[{item.source}] {item.title} — {item.url}"
                for item in items[:20]
            )

        elif name == "crypto_prices":
            if not t.get("coingecko"):
                return "CoinGecko not available."
            coins = inputs.get("coins", ["bitcoin", "solana", "ethereum"])
            try:
                prices = t["coingecko"].get_prices(coins=coins)
                lines = []
                for p in prices:
                    sign = "+" if p.change_24h >= 0 else ""
                    lines.append(
                        f"{p.name} ({p.symbol.upper()}): ${p.price_usd:,.2f} ({sign}{p.change_24h:.1f}% 24h)"
                    )
                return "\n".join(lines) if lines else "Ingen prisdata."
            except Exception as e:
                return f"CoinGecko error: {e}"

        elif name == "brreg_find_leads":
            if not t.get("brreg"):
                return "brreg ikke tilgjengelig."
            leads = t["brreg"].find_leads(
                industry_code=inputs.get("industry_code", "62"),
                municipality=inputs.get("municipality", ""),
                min_employees=inputs.get("min_employees", 5),
                max_employees=inputs.get("max_employees", 50),
                max_results=inputs.get("max_results", 20),
            )
            if not leads:
                return "Ingen bedrifter funnet i Brønnøysund."
            lines = [f"{len(leads)} norske bedrifter funnet:"]
            for l in leads:
                lines.append(
                    f"- {l['name']} | {l['employees']} ansatte | {l['municipality']} | {l.get('website','') or 'ingen nettside'}"
                )
            return "\n".join(lines)

        elif name == "brreg_get_company":
            if not t.get("brreg"):
                return "brreg ikke tilgjengelig."
            c = t["brreg"].get_company(inputs["org_number"])
            if not c:
                return f"Fant ikke bedrift med org.nummer {inputs['org_number']}"
            return (
                f"{c['name']}\n"
                f"Org.nr: {c['org_number']}\n"
                f"Ansatte: {c['employees']}\n"
                f"Bransje: {c['industry']}\n"
                f"Adresse: {c['address']}\n"
                f"Nettside: {c.get('website','—')}\n"
                f"E-post: {c.get('email','—')}"
            )


        elif name == "github_list_repos":
            if not t.get("github"):
                return "GitHub ikke konfigurert (GITHUB_TOKEN mangler)."
            repos = t["github"].list_repos()
            parts = []
            for r in repos:
                parts.append("- " + r["name"] + " (" + r["url"] + ")")
            return "GitHub repos (" + str(len(repos)) + "):" + chr(10) + chr(10).join(parts)

        elif name == "github_push_file":
            if not t.get("github"):
                return "GitHub ikke konfigurert."
            result = t["github"].push_file(
                repo=inputs["repo"],
                path=inputs["path"],
                content=inputs["content"],
                message=inputs["message"],
                branch=inputs.get("branch", "main"),
            )
            return f"Fil pushet til GitHub: {result['url']} | SHA: {result['sha'][:7]}"

        elif name == "github_create_repo":
            if not t.get("github"):
                return "GitHub ikke konfigurert."
            result = t["github"].create_repo(
                name=inputs["name"],
                description=inputs.get("description", ""),
                private=inputs.get("private", False),
            )
            return f"Repo opprettet: {result['url']}"

        elif name == "stripe_create_link":
            if not t.get("stripe"):
                return "Stripe ikke konfigurert (STRIPE_SECRET_KEY mangler)."
            result = t["stripe"].create_payment_link(
                amount_cents=inputs["amount_nok"] * 100,
                currency="nok",
                product_name=inputs["product_name"],
            )
            return f"Stripe payment link: {result['url']} | {inputs['amount_nok']} NOK | {inputs['product_name']}"

        elif name == "minimax_chat":
            if not t.get("minimax"):
                return "MiniMax not configured (MINIMAX_API_KEY missing)."
            return t["minimax"].chat(
                prompt=inputs["prompt"],
                system=inputs.get("system", "Du er Jarvis, en AI-assistent."),
                model=inputs.get("model", "MiniMax-M2.5-highspeed"),
                max_tokens=inputs.get("max_tokens", 1000),
            )

        elif name == "minimax_tts":
            if not t.get("minimax"):
                return "MiniMax not configured (MINIMAX_API_KEY missing)."
            path = t["minimax"].text_to_speech(
                text=inputs["text"],
                voice_id=inputs.get("voice_id", "Insightful_Speaker"),
                model=inputs.get("model", "speech-2.8-turbo"),
                emotion=inputs.get("emotion", "neutral"),
                language_boost=inputs.get("language_boost", "auto"),
            )
            return f"MiniMax TTS lagret: {path}"

        elif name == "minimax_video":
            if not t.get("minimax"):
                return "MiniMax not configured (MINIMAX_API_KEY missing)."
            result = t["minimax"].generate_video(
                prompt=inputs["prompt"],
                resolution=inputs.get("resolution", "1080P"),
                duration=inputs.get("duration", 6),
                image_url=inputs.get("image_url"),
                wait=True,
            )
            if result.get("error"):
                return f"MiniMax video feil: {result['error']}"
            if result.get("status") == "success":
                return f"Video ferdig: {result.get('video_url', 'se task_id: ' + result.get('task_id', ''))}"
            return f"Video status: {result.get('status')} | task_id: {result.get('task_id')}"

        elif name == "minimax_music":
            if not t.get("minimax"):
                return "MiniMax not configured (MINIMAX_API_KEY missing)."
            path = t["minimax"].generate_music(
                prompt=inputs["prompt"],
                lyrics=inputs.get("lyrics"),
                instrumental=inputs.get("instrumental", False),
            )
            return f"Musikk lagret: {path}"

        else:
            return f"Unknown tool: {name}"

    except Exception as e:
        logger.error(f"Tool '{name}' failed: {e}", exc_info=True)
        return f"Tool '{name}' failed: {e}"


# ── API call with retry + circuit breaker ─────────────────────────────────────

async def _call_api_with_retry(
    client: anthropic.AsyncAnthropic,
    system_prompt: str,
    api_messages: list[dict],
    chat_id: str,
    telegram_send: TelegramSendFn,
):
    global _consecutive_errors, _circuit_open_until

    if time.monotonic() < _circuit_open_until:
        remaining = int(_circuit_open_until - time.monotonic())
        raise RuntimeError(f"Circuit breaker open — API paused for {remaining}s more.")

    max_attempts = 5
    backoff = 1

    for attempt in range(max_attempts):
        try:
            response = await client.messages.create(
                model=CLAUDE_SONNET,
                max_tokens=8096,
                system=system_prompt,
                tools=TOOLS,
                messages=api_messages,
            )
            _consecutive_errors = 0
            return response

        except anthropic.RateLimitError:
            if attempt < max_attempts - 1:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 16)
            else:
                _consecutive_errors += 1
                _check_circuit_breaker(chat_id, telegram_send)
                raise

        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            logger.error("Claude API auth failed — ANTHROPIC_API_KEY invalid.")
            raise

        except Exception:
            _consecutive_errors += 1
            _check_circuit_breaker(chat_id, telegram_send)
            raise


def _check_circuit_breaker(chat_id: str, telegram_send: TelegramSendFn) -> None:
    global _circuit_open_until
    if _consecutive_errors >= CIRCUIT_BREAKER_THRESHOLD:
        _circuit_open_until = time.monotonic() + CIRCUIT_BREAKER_COOLDOWN
        logger.error(f"Circuit breaker OPENED after {_consecutive_errors} errors.")
        asyncio.create_task(
            telegram_send(
                chat_id,
                f"⚠️ *Circuit breaker åpnet* — API stoppet etter {_consecutive_errors} feil.\n"
                f"Prøver igjen om {CIRCUIT_BREAKER_COOLDOWN // 60} minutter.",
                None,
            )
        )


async def _groq_fallback(user_message: str, system_prompt: str) -> str:
    logger.warning("Falling back to Groq — Claude API key invalid.")
    try:
        from tools.groq_client import chat as groq_chat
        response = groq_chat(
            prompt=user_message,
            system=system_prompt[:3000] + "\n\nNOTE: Running in fallback mode. No tools available. Tell Nicholas that the Anthropic API key on Hetzner needs to be updated.",
            max_tokens=1024,
            temperature=0.5,
        )
        return f"⚠️ _(Kjører i backup-modus — Claude API-key feil)_\n\n{response}"
    except Exception as e:
        logger.error(f"Groq fallback also failed: {e}")
        return "❌ Jarvis er offline.\n\nAnthropic API-key på Hetzner er feil. Oppdater ENV_FILE i GitHub Secrets."


# ── Main run loop ─────────────────────────────────────────────────────────────

async def run(
    user_message: str,
    chat_id: str,
    telegram_send: TelegramSendFn,
    agent_name: str = "jordan",
) -> str:
    """
    Run the agent loop for a single user message.

    Returns the agent's final text response.
    """
    client = anthropic.AsyncAnthropic()

    messages = _load_history(chat_id)
    messages.append({"role": "user", "content": user_message})

    # Inject smart_memory context for this specific message
    system_prompt = _build_system_prompt(agent_name)
    try:
        from memory.smart_memory import get_context, save_chat
        smart_ctx = get_context(user_message, max_tokens=400)
        if smart_ctx:
            system_prompt += smart_ctx
        save_chat("user", user_message[:500])
    except Exception:
        pass

    MAX_TURNS = 25

    for turn in range(MAX_TURNS):
        api_messages = _trim_for_api(messages)

        try:
            response = await _call_api_with_retry(
                client=client,
                system_prompt=system_prompt,
                api_messages=api_messages,
                chat_id=chat_id,
                telegram_send=telegram_send,
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            _save_history(chat_id, messages)
            return await _groq_fallback(user_message, system_prompt)
        except RuntimeError as exc:
            _save_history(chat_id, messages)
            return f"❌ {exc}"

        text_blocks = [b.text for b in response.content if hasattr(b, "text")]
        tool_uses   = [b for b in response.content if b.type == "tool_use"]
        serialized  = _serialize_content(response.content)

        if response.stop_reason == "end_turn" or not tool_uses:
            messages.append({"role": "assistant", "content": serialized})
            _save_history(chat_id, messages)

            final_text = "\n".join(text_blocks) if text_blocks else "✅"

            # Save to memory
            t = _get_tools()
            if t.get("memory_manager"):
                try:
                    t["memory_manager"].add_conversation_summary(
                        f"{user_message[:80]} → {final_text[:120]}"
                    )
                except Exception:
                    pass
            try:
                from memory.smart_memory import save_chat
                save_chat("assistant", final_text[:500])
            except Exception:
                pass

            return final_text

        # Execute tool calls
        tool_results = []
        for tool_use in tool_uses:
            logger.info(f"Tool: {tool_use.name} — {tool_use.input}")
            result = await _execute_tool(
                name=tool_use.name,
                inputs=tool_use.input,
                chat_id=chat_id,
                telegram_send=telegram_send,
            )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result,
            })

        messages.append({"role": "assistant", "content": serialized})
        messages.append({"role": "user", "content": tool_results})

    _save_history(chat_id, messages)
    return "⚠️ Nådde maks antall steg. Prøv igjen eller reformuler forespørselen."
