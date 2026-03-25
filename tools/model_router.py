"""
Model Router — Jarvis decides which AI to use before starting a task.

Routing logic:
  Groq (free, fast)    — research, search, summaries, leads, news, drafts
  Gemini Flash (free)  — long documents, PDFs, large context
  Claude Sonnet        — code, build, deploy, complex decisions, tool-use loop
  Ollama (free, local) — simple generation when Groq is rate-limited

Jarvis uses this before every task. Never hardcode model names elsewhere.
"""
import logging
import os

logger = logging.getLogger(__name__)

# Model identifiers
GROQ_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.0-flash-exp"
CLAUDE_MODEL = "claude-sonnet-4-6"
OLLAMA_MODEL = "llama3.3"

# Task type → model mapping
_TASK_ROUTING: dict[str, str] = {
    "research": "groq",
    "search": "groq",
    "news": "groq",
    "leads": "groq",
    "scan": "groq",
    "summary": "groq",
    "summarize": "groq",
    "draft": "groq",
    "email draft": "groq",
    "analyze market": "groq",
    "trading signal": "groq",
    "opportunity": "groq",
    "find": "groq",
    "list": "groq",
    "translate": "groq",
    "classify": "groq",
    "score": "groq",
    "pitch": "groq",
    "long document": "gemini",
    "pdf": "gemini",
    "large file": "gemini",
    "read document": "gemini",
    "analyze document": "gemini",
    "build": "claude",
    "code": "claude",
    "deploy": "claude",
    "implement": "claude",
    "create app": "claude",
    "fix bug": "claude",
    "debug": "claude",
    "architecture": "claude",
    "design system": "claude",
    "write code": "claude",
    "agent": "claude",
    "strategy": "claude",
}


def choose_model(task: str) -> str:
    """
    Choose the best model for a task based on keywords.

    Returns one of: 'groq', 'gemini', 'claude', 'ollama'

    Usage:
        model = choose_model("research Norwegian SMEs")  # → 'groq'
        model = choose_model("build and deploy React app")  # → 'claude'
    """
    task_lower = task.lower()

    # Long tasks → Gemini (1M context, free)
    if len(task) > 4000:
        logger.debug(f"model_router: task is long ({len(task)} chars) → gemini")
        return "gemini"

    # Keyword matching — most specific wins
    for keyword, model in _TASK_ROUTING.items():
        if keyword in task_lower:
            logger.debug(f"model_router: '{keyword}' matched → {model}")
            return model

    # Check if Ollama is available (local, free, no rate limits)
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    if _ollama_available(ollama_url):
        logger.debug("model_router: no keyword match, Ollama available → ollama")
        return "ollama"

    # Default: Groq (free) for sub-agents, Claude for main agent
    logger.debug("model_router: no keyword match → groq (default)")
    return "groq"


def choose_model_id(task: str) -> str:
    """Returns the actual model ID string for use in API calls."""
    model_type = choose_model(task)
    return {
        "groq": GROQ_MODEL,
        "gemini": GEMINI_MODEL,
        "claude": CLAUDE_MODEL,
        "ollama": OLLAMA_MODEL,
    }.get(model_type, GROQ_MODEL)


def _ollama_available(url: str) -> bool:
    """Quick check if Ollama is running locally."""
    try:
        import httpx
        r = httpx.get(f"{url}/api/tags", timeout=1.0)
        return r.status_code == 200
    except Exception:
        return False


def get_model_summary() -> str:
    """Human-readable explanation of routing for a given context."""
    ollama_ok = _ollama_available(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    return (
        f"Model routing active:\n"
        f"  Groq (free): research, search, leads, news, drafts\n"
        f"  Gemini (free): long documents, PDFs\n"
        f"  Claude: code, build, deploy, complex decisions\n"
        f"  Ollama (local): {'AVAILABLE' if ollama_ok else 'offline'}"
    )
