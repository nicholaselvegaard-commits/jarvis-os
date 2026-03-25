"""
Ollama local LLM client.
Connects to Ollama running on the Hetzner server (or localhost for dev).

Setup:
  1. SSH to Hetzner: ssh root@<server-ip>
  2. curl -fsSL https://ollama.ai/install.sh | sh
  3. ollama pull llama3.3
  4. ollama serve  (starts on port 11434)
  5. Set OLLAMA_BASE_URL=http://<server-ip>:11434 in .env

Local dev: OLLAMA_BASE_URL=http://localhost:11434
"""
import logging
import os

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.3"


def _base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def chat(
    prompt: str,
    model: str | None = None,
    system: str | None = None,
    temperature: float = 0.7,
    timeout: float = 120.0,
) -> str:
    """
    Send a prompt to Ollama and return the response text.

    Args:
        prompt: User message
        model: Model name (default: llama3.3). Must be pulled first.
        system: Optional system prompt
        temperature: Sampling temperature
        timeout: Request timeout in seconds

    Returns:
        Response text
    """
    model = model or os.getenv("OLLAMA_DEFAULT_MODEL", DEFAULT_MODEL)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "options": {"temperature": temperature},
        "stream": False,
    }

    try:
        resp = httpx.post(
            f"{_base_url()}/api/chat",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("message", {}).get("content", "")
        logger.info(f"Ollama ({model}): {len(text)} chars")
        return text
    except httpx.ConnectError:
        raise RuntimeError(
            f"Cannot connect to Ollama at {_base_url()}. "
            "Is it running? Set OLLAMA_BASE_URL in .env."
        )


def list_models() -> list[str]:
    """Return list of locally available Ollama models."""
    try:
        resp = httpx.get(f"{_base_url()}/api/tags", timeout=5.0)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
    except Exception as exc:
        logger.warning(f"Failed to list Ollama models: {exc}")
        return []


def is_available() -> bool:
    """Return True if Ollama is reachable."""
    try:
        httpx.get(f"{_base_url()}/api/tags", timeout=3.0)
        return True
    except Exception:
        return False
