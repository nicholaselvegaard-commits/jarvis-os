"""
Gemini client — med Groq-fallback når Gemini-nøkkel er utløpt.

Modeller:
- gemini-2.0-flash    : raskest, gratis
- gemini-1.5-pro      : best kvalitet, stor kontekst
- gemini-1.5-flash    : rask + billig
- groq/llama-3.3-70b  : fallback (gratis, veldig rask)
"""
import logging
import os
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

GeminiModel = Literal["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
DEFAULT_MODEL: GeminiModel = "gemini-2.0-flash"

_gemini_working: bool | None = None  # cached health check


def ask(
    prompt: str,
    system: str | None = None,
    model: GeminiModel = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """
    Send a prompt to Gemini. Falls back to Groq (llama-3.3-70b) if Gemini fails.

    Returns:
        Response text string
    """
    global _gemini_working
    if _gemini_working is not False:
        try:
            result = _ask_gemini(prompt, system=system, model=model,
                                  temperature=temperature, max_tokens=max_tokens)
            _gemini_working = True
            return result
        except Exception as e:
            err_str = str(e).lower()
            if "expired" in err_str or "invalid" in err_str or "api_key" in err_str:
                logger.warning(f"Gemini API key issue, switching to Groq: {e}")
                _gemini_working = False
            else:
                logger.warning(f"Gemini failed ({e}), trying Groq fallback")

    # Groq fallback
    return _ask_groq(prompt, system=system, temperature=temperature, max_tokens=min(max_tokens, 8000))


def _ask_gemini(
    prompt: str,
    system: str | None,
    model: str,
    temperature: float,
    max_tokens: int,
) -> str:
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set")

    payload: dict = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    url = f"{BASE_URL}/{model}:generateContent?key={GEMINI_API_KEY}"
    with httpx.Client(timeout=60) as client:
        r = client.post(url, json=payload)
        if not r.is_success:
            err = r.json().get("error", {})
            raise RuntimeError(f"Gemini {r.status_code}: {err.get('message', r.text[:200])}")
        data = r.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response: {data}") from exc


def _ask_groq(
    prompt: str,
    system: str | None,
    temperature: float,
    max_tokens: int,
) -> str:
    """Groq API — llama-3.3-70b, gratis og rask."""
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set — ingen fallback tilgjengelig")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    with httpx.Client(timeout=30) as client:
        r = client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        if not r.is_success:
            raise RuntimeError(f"Groq {r.status_code}: {r.text[:200]}")
        result = r.json()["choices"][0]["message"]["content"]
        logger.info("Groq fallback used successfully")
        return result


def summarize_long(text: str, instruction: str = "Summarize this concisely") -> str:
    """Summarize a long document. Uses Gemini 1.5-pro if available, else Groq."""
    try:
        return _ask_gemini(
            prompt=f"{instruction}:\n\n{text}",
            system=None,
            model="gemini-1.5-pro",
            temperature=0.3,
            max_tokens=2048,
        )
    except Exception:
        return _ask_groq(
            prompt=f"{instruction}:\n\n{text[:15000]}",
            system=None,
            temperature=0.3,
            max_tokens=2048,
        )
