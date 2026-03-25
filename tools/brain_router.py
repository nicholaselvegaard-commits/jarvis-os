"""
brain_router.py -- DEPRECATED. Use tools/model_router.py instead.
All routing logic consolidated into model_router.py.
"""
from tools.model_router import choose_model, choose_model_id, GROQ_MODEL, GEMINI_MODEL, CLAUDE_MODEL

TIERS = {
    "free":   GROQ_MODEL,
    "fast":   "claude-haiku-4-5-20251001",
    "smart":  CLAUDE_MODEL,
    "genius": "claude-opus-4-6",
}

def route(task_description: str, override_tier=None) -> str:
    """Legacy. Use model_router.choose_model() for new code."""
    if override_tier:
        return TIERS.get(override_tier, GROQ_MODEL)
    return choose_model_id(task_description)
