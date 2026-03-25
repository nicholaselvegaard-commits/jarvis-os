"""
Voice transcription using faster-whisper (runs fully locally, no API key needed).

First call downloads the model (~145MB for "base") to:
  C:/Users/<user>/.cache/huggingface/hub/

Supports OGG/OPUS (Telegram voice), MP3, WAV, MP4, etc.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Model size tradeoff:
#   tiny   ~75MB   — fast, less accurate
#   base   ~145MB  — good balance (default)
#   small  ~466MB  — more accurate, slower
#   medium ~1.5GB  — high accuracy
MODEL_SIZE = "base"

_model = None  # Lazy-loaded on first use


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        logger.info(f"Loading Whisper model '{MODEL_SIZE}' (downloads on first run)...")
        _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
        logger.info("Whisper model loaded.")
    return _model


def transcribe(audio_path: str, language: str = "no") -> str:
    """
    Transcribe an audio file to text.

    Args:
        audio_path: Path to the audio file (OGG, MP3, WAV, MP4, etc.)
        language:   Language hint — "no" for Norwegian, "en" for English.
                    None = auto-detect (slightly slower).

    Returns:
        Transcribed text string.
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    model = _get_model()
    segments, info = model.transcribe(
        str(path),
        language=language,
        beam_size=5,
        vad_filter=True,          # Skip silent parts automatically
        vad_parameters={"min_silence_duration_ms": 500},
    )

    text = " ".join(segment.text.strip() for segment in segments).strip()
    logger.info(
        f"Transcribed {path.name} ({info.duration:.1f}s, lang={info.language}): {text[:80]}..."
    )
    return text
