"""
Whisper speech-to-text. Uses Groq for fastest results, falls back to OpenAI.
Accepts audio files or Telegram voice messages.
"""
import logging
import os
from pathlib import Path

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)


@with_retry()
def transcribe(audio_path: str | Path, language: str | None = None) -> str:
    """
    Transcribe an audio file to text.

    Args:
        audio_path: Path to audio file (.mp3, .wav, .m4a, .ogg, .webm)
        language: ISO language code (e.g. 'no', 'en'). None = auto-detect.

    Returns:
        Transcribed text
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # Try Groq first (fastest, free)
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        try:
            return _transcribe_groq(audio_path, language, groq_key)
        except Exception as exc:
            logger.warning(f"Groq transcription failed, falling back to OpenAI: {exc}")

    # Fallback: OpenAI Whisper
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        return _transcribe_openai(audio_path, language, openai_key)

    raise ValueError("No transcription API key configured (GROQ_API_KEY or OPENAI_API_KEY)")


def _transcribe_groq(path: Path, language: str | None, key: str) -> str:
    with open(path, "rb") as f:
        data: dict = {"model": "whisper-large-v3"}
        if language:
            data["language"] = language
        resp = httpx.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (path.name, f, "audio/mpeg")},
            data=data,
            timeout=120.0,
        )
    resp.raise_for_status()
    return resp.json().get("text", "")


def _transcribe_openai(path: Path, language: str | None, key: str) -> str:
    with open(path, "rb") as f:
        data: dict = {"model": "whisper-1", "response_format": "text"}
        if language:
            data["language"] = language
        resp = httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": (path.name, f, "audio/mpeg")},
            data=data,
            timeout=120.0,
        )
    resp.raise_for_status()
    return resp.text.strip()
