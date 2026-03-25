"""
OpenRouter client — access 200+ AI models via a single API.
Best for: comparing models, using cheap alternatives, accessing Gemini/DeepSeek.
"""
import logging
import os

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-2.0-flash-exp:free"


def _headers() -> dict:
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        raise ValueError("OPENROUTER_API_KEY not set in .env")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://nicholasai.com",
        "X-Title": "NicholasAgent",
    }


@with_retry()
def chat(
    prompt: str,
    model: str | None = None,
    system: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """
    Send a prompt to any model via OpenRouter.

    Args:
        prompt: User message
        model: OpenRouter model ID (e.g. "google/gemini-2.0-flash-exp:free")
        system: Optional system prompt
        temperature: Sampling temperature
        max_tokens: Max output tokens

    Returns:
        Response text
    """
    model = model or os.getenv("OPENROUTER_DEFAULT_MODEL", DEFAULT_MODEL)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = httpx.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers=_headers(),
        json={"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
        timeout=120.0,
    )
    if resp.status_code == 429:
        raise RuntimeError(f"OpenRouter rate limited: {resp.text[:200]}")
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    logger.info(f"OpenRouter ({model}): {len(text)} chars")
    return text


@with_retry()
def list_free_models() -> list[dict]:
    """Return list of currently free models on OpenRouter."""
    resp = httpx.get(f"{OPENROUTER_BASE_URL}/models", headers=_headers(), timeout=10.0)
    resp.raise_for_status()
    models = resp.json().get("data", [])
    return [m for m in models if float(m.get("pricing", {}).get("prompt", 1)) == 0]
