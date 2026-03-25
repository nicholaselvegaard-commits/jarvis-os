"""
Jarvis's voice — ElevenLabs TTS with Jarvis Belfort personality settings.

Voice: energetic, confident American male salesman.
Default voice ID: Adam (pNInz6obpgDQGcFmaJgB) — swap via JORDAN_VOICE_ID in .env.

Usage:
    from tools.jarvis_voice import speak
    audio_path = speak("Vi eier dette markedet, hør her!")
"""
import logging
import os
from pathlib import Path

from tools.elevenlabs import text_to_speech

logger = logging.getLogger(__name__)

# Jarvis Belfort style: confident American male, high energy
# Default: Adam — clean, authoritative American voice
# Change by setting JORDAN_VOICE_ID in .env
JORDAN_VOICE_ID = os.getenv("JORDAN_VOICE_ID", "pNInz6obpgDQGcFmaJgB")

# Low stability = more expressive/emotional, High similarity = stays in character
JORDAN_STABILITY = 0.30        # energetic, dynamic — like a pitch call
JORDAN_SIMILARITY_BOOST = 0.85 # stays recognizably "Jarvis"
JORDAN_MODEL = "eleven_turbo_v2_5"  # lowest latency

VOICE_DIR = Path("memory/voice_cache")


def speak(text: str, output_path: str | None = None) -> str:
    """
    Convert text to Jarvis's voice.

    Args:
        text: What Jarvis says
        output_path: Where to save .mp3 (auto-generated if None)

    Returns:
        Path to the .mp3 file
    """
    VOICE_DIR.mkdir(parents=True, exist_ok=True)

    if not output_path:
        import uuid
        output_path = str(VOICE_DIR / f"jarvis_{str(uuid.uuid4())[:8]}.mp3")

    path = text_to_speech(
        text=text,
        voice_id=JORDAN_VOICE_ID,
        model=JORDAN_MODEL,
        output_path=output_path,
        stability=JORDAN_STABILITY,
        similarity_boost=JORDAN_SIMILARITY_BOOST,
    )
    logger.info(f"Jarvis spoke: {len(text)} chars → {path}")
    return path


def speak_intro() -> str:
    """Jarvis introduces himself — used for /ring command."""
    intro = (
        "Hey! Jarvis here. What are we building today? "
        "Talk to me, I'm listening. Let's make some money."
    )
    return speak(intro)


def cleanup_old_voice_files(max_files: int = 20) -> None:
    """Keep voice cache small — delete oldest files beyond max_files."""
    if not VOICE_DIR.exists():
        return
    files = sorted(VOICE_DIR.glob("jarvis_*.mp3"), key=lambda f: f.stat().st_mtime)
    for f in files[:-max_files]:
        try:
            f.unlink()
        except Exception:
            pass
