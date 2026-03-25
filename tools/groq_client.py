"""
Groq API client — fast, free-tier inference for Llama and Mixtral models.
Free tier: 14,400 req/day, 500K tokens/day.
"""
import logging
import os

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"


def _headers() -> dict:
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        raise ValueError("GROQ_API_KEY not set in .env")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


@with_retry()
def chat(
    prompt: str,
    model: str | None = None,
    system: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    """
    Send a prompt to Groq and return the response text.

    Args:
        prompt: User message
        model: Groq model (default: llama-3.3-70b-versatile)
        system: Optional system prompt
        temperature: Sampling temperature
        max_tokens: Max output tokens

    Returns:
        Response text
    """
    model = model or os.getenv("GROQ_DEFAULT_MODEL", DEFAULT_MODEL)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = httpx.post(
        f"{GROQ_BASE_URL}/chat/completions",
        headers=_headers(),
        json={
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=60.0,
    )
    if resp.status_code == 429:
        raise RuntimeError(f"Groq rate limited: {resp.text[:200]}")
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    logger.info(f"Groq ({model}): {len(text)} chars")
    return text


@with_retry()
def transcribe(audio_path: str, model: str = "whisper-large-v3") -> str:
    """
    Transcribe audio using Whisper on Groq (fastest available).

    Args:
        audio_path: Local path to audio file (.mp3, .wav, .m4a, etc.)
        model: Whisper model variant

    Returns:
        Transcribed text
    """
    with open(audio_path, "rb") as f:
        resp = httpx.post(
            f"{GROQ_BASE_URL}/audio/transcriptions",
            headers={"Authorization": _headers()["Authorization"]},
            files={"file": (audio_path, f, "audio/mpeg")},
            data={"model": model},
            timeout=120.0,
        )
    resp.raise_for_status()
    return resp.json().get("text", "")
