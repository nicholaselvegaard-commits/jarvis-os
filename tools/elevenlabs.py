"""
ElevenLabs text-to-speech and voice cloning.
Generates realistic speech for agents, videos, and podcasts.
"""
import logging
import os
from pathlib import Path

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel — clear, neutral
DEFAULT_MODEL = "eleven_turbo_v2_5"

OUTPUT_DIR = Path("outputs")


def _headers() -> dict:
    key = os.getenv("ELEVENLABS_API_KEY", "")
    if not key:
        raise ValueError("ELEVENLABS_API_KEY not set in .env")
    return {"xi-api-key": key}


@with_retry()
def text_to_speech(
    text: str,
    voice_id: str | None = None,
    model: str = DEFAULT_MODEL,
    output_path: str | None = None,
    stability: float = 0.5,
    similarity_boost: float = 0.75,
) -> str:
    """
    Convert text to speech.

    Args:
        text: Text to synthesize
        voice_id: ElevenLabs voice ID (default: Rachel)
        model: Model ID (turbo_v2_5 for low latency, multilingual_v2 for Norwegian)
        output_path: Where to save the .mp3 (auto-generated if None)
        stability: Voice stability 0-1
        similarity_boost: Voice similarity 0-1

    Returns:
        Path to generated audio file
    """
    voice = voice_id or os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    resp = httpx.post(
        f"{ELEVENLABS_BASE}/text-to-speech/{voice}",
        headers={**_headers(), "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": model,
            "voice_settings": {"stability": stability, "similarity_boost": similarity_boost},
        },
        timeout=60.0,
    )
    resp.raise_for_status()

    if not output_path:
        import uuid
        output_path = str(OUTPUT_DIR / f"speech_{str(uuid.uuid4())[:8]}.mp3")

    Path(output_path).write_bytes(resp.content)
    logger.info(f"ElevenLabs TTS: {len(text)} chars → {output_path}")
    return output_path


@with_retry()
def list_voices() -> list[dict]:
    """Return available voices on this ElevenLabs account."""
    resp = httpx.get(f"{ELEVENLABS_BASE}/voices", headers=_headers(), timeout=10.0)
    resp.raise_for_status()
    return resp.json().get("voices", [])


@with_retry()
def get_usage() -> dict:
    """Return current subscription usage (character count)."""
    resp = httpx.get(f"{ELEVENLABS_BASE}/user/subscription", headers=_headers(), timeout=10.0)
    resp.raise_for_status()
    return resp.json()
