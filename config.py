"""
NEXUS — samlet konfigurasjon.
Alle miljøvariabler hentes herfra.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Last .env fra prosjektrot
load_dotenv(Path(__file__).parent / ".env")

# ── AI ────────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

CLAUDE_SONNET = "claude-sonnet-4-6"
CLAUDE_HAIKU  = "claude-haiku-4-5-20251001"

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_TOKEN         = os.getenv("TELEGRAM_TOKEN", TELEGRAM_BOT_TOKEN)  # alias
TELEGRAM_OWNER_CHAT_ID = os.getenv("TELEGRAM_OWNER_CHAT_ID", "")
ALLOWED_CHAT_IDS: set[str] = set(
    x.strip() for x in os.getenv("ALLOWED_CHAT_IDS", "").split(",") if x.strip()
)

# ── E-post ────────────────────────────────────────────────────────────────────
EMAIL_ADDRESS   = os.getenv("EMAIL_ADDRESS", "nicholas.elvegaard@gmail.com")
EMAIL_PASSWORD  = os.getenv("EMAIL_PASSWORD", "")
EMAIL_IMAP_HOST = os.getenv("EMAIL_IMAP_HOST", "imap.gmail.com")
EMAIL_IMAP_PORT = int(os.getenv("EMAIL_IMAP_PORT", "993"))
SMTP_HOST       = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT       = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER       = os.getenv("SMTP_USER", EMAIL_ADDRESS)
SMTP_PASSWORD   = os.getenv("SMTP_PASSWORD", EMAIL_PASSWORD)
EMAIL_FROM      = os.getenv("EMAIL_FROM", EMAIL_ADDRESS)
RESEND_API_KEY  = os.getenv("RESEND_API_KEY", "")

# Jarvis sin egen e-post
JORDAN_SMTP_USER = os.getenv("JORDAN_SMTP_USER", "jordan.develepor@outlook.com")
EMAIL_USER       = os.getenv("EMAIL_USER", JORDAN_SMTP_USER)
EMAIL_PASS       = os.getenv("EMAIL_PASS", os.getenv("EMAIL_PASSWORD", ""))
EMAIL_SMTP_HOST  = os.getenv("EMAIL_SMTP_HOST", "smtp-mail.outlook.com")
EMAIL_SMTP_PORT  = int(os.getenv("EMAIL_SMTP_PORT", "587"))

# ── GitHub ────────────────────────────────────────────────────────────────────
GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")

# ── Stripe ────────────────────────────────────────────────────────────────────
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")

# ── Search ────────────────────────────────────────────────────────────────────
BRAVE_API_KEY   = os.getenv("BRAVE_API_KEY", "")
TAVILY_API_KEY  = os.getenv("TAVILY_API_KEY", "")
EXA_API_KEY     = os.getenv("EXA_API_KEY", "")

# ── Lead generation ───────────────────────────────────────────────────────────
APOLLO_API_KEY  = os.getenv("APOLLO_API_KEY", "")
HUNTER_API_KEY  = os.getenv("HUNTER_API_KEY", "")

# ── Social ────────────────────────────────────────────────────────────────────
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")

# ── Misc integrasjoner ────────────────────────────────────────────────────────
MAKE_API_KEY       = os.getenv("MAKE_API_KEY", "")
SUPABASE_URL       = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY  = os.getenv("SUPABASE_ANON_KEY", "")
VERCEL_TOKEN       = os.getenv("VERCEL_TOKEN", "")
FIRECRAWL_API_KEY  = os.getenv("FIRECRAWL_API_KEY", "")
GUMROAD_ACCESS_TOKEN = os.getenv("GUMROAD_ACCESS_TOKEN", "")
PRODUCT_HUNT_API_KEY = os.getenv("PRODUCT_HUNT_API_KEY", "")
NEWSAPI_KEY        = os.getenv("NEWSAPI_KEY", "")

# ── MCP ───────────────────────────────────────────────────────────────────────
MCP_SECRET     = os.getenv("MCP_SECRET", "jordan-manus-secret-2026")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://89.167.100.7:8001")

# ── Infrastruktur ─────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent
MEMORY_DIR     = BASE_DIR / "memory"
AGENTS_DIR     = BASE_DIR / "agents"
KNOWLEDGE_DIR  = BASE_DIR / "knowledge"

MEMORY_DIR.mkdir(exist_ok=True)
KNOWLEDGE_DIR.mkdir(exist_ok=True)

DATABASE_URL   = os.getenv("DATABASE_URL", f"sqlite:///{MEMORY_DIR}/nexus.db")
KB_DIR         = os.getenv("KB_DIR", str(KNOWLEDGE_DIR))

# ── Browser automation ────────────────────────────────────────────────────────
PLAYWRIGHT_BROWSERS_PATH = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "/opt/nexus/.playwright")
