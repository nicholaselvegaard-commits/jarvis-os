"""
MiniMax AI — full integrasjon for NEXUS.

Modeller:
  LLM:   MiniMax-M2.5-highspeed (rask/billig), MiniMax-M2.7 (kraftig)
  TTS:   speech-2.8-turbo (rask), speech-2.8-hd (kvalitet) — 40 språk, 7 emosjoner
  Video: MiniMax-Hailuo-2.3 (1080p, tekst-/bildetil-video)
  Musikk: music-2.5+ (instrumentell + vokal, alle sjangre)

Auth: Authorization: Bearer MINIMAX_API_KEY
Base URL: https://api.minimax.io
Anthropic-compat: https://api.minimax.io/anthropic
"""

import base64
import logging
import os
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
BASE = "https://api.minimax.io"

OUTPUT_DIR = Path("/opt/nexus/output/minimax")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }


def _check_key() -> Optional[str]:
    if not MINIMAX_API_KEY:
        return "MINIMAX_API_KEY mangler — legg til i .env"
    return None


# ── LLM ───────────────────────────────────────────────────────────────────────

def chat(
    prompt: str,
    system: str = "Du er Jarvis, en AI-assistent.",
    model: str = "MiniMax-M2.5-highspeed",
    max_tokens: int = 1000,
) -> str:
    """
    Chat med MiniMax LLM via Anthropic-kompatibel API.

    Args:
        prompt:     Brukermelding
        system:     System-prompt
        model:      MiniMax-M2.5-highspeed | MiniMax-M2.5 | MiniMax-M2.7 | MiniMax-M2.7-highspeed
        max_tokens: Maks tokens i svar

    Returns:
        Tekstsvar fra modellen
    """
    err = _check_key()
    if err:
        return err
    try:
        import anthropic
        client = anthropic.Anthropic(
            api_key=MINIMAX_API_KEY,
            base_url="https://api.minimax.io/anthropic",
        )
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text if msg.content else ""
    except Exception as e:
        logger.error(f"minimax.chat feil: {e}")
        return f"minimax.chat feil: {e}"


# ── TTS ───────────────────────────────────────────────────────────────────────

def text_to_speech(
    text: str,
    voice_id: str = "Insightful_Speaker",
    model: str = "speech-2.8-turbo",
    emotion: str = "neutral",
    language_boost: str = "auto",
    output_path: Optional[str] = None,
) -> str:
    """
    Generer tale fra tekst med MiniMax TTS.

    40 språk, 7 emosjoner. Alternativ til ElevenLabs.

    Args:
        text:          Tekst å syntetisere (maks 10 000 tegn)
        voice_id:      Stemme-ID. Engelske: Insightful_Speaker, Graceful_Lady, Lucky_Robot
        model:         speech-2.8-turbo (rask) | speech-2.8-hd (kvalitet)
        emotion:       neutral | happy | sad | angry | fear | surprise | disgust
        language_boost: auto | en-US | no | zh-CN
        output_path:   Lokal filbane å lagre til (mp3). Auto-genereres hvis None.

    Returns:
        Filbane til lagret lydfil, eller feilmelding
    """
    err = _check_key()
    if err:
        return err
    if len(text) > 10000:
        return "Tekst er for lang (maks 10 000 tegn)"

    try:
        payload = {
            "model": model,
            "text": text,
            "stream": False,
            "output_format": "hex",
            "language_boost": language_boost,
            "voice_setting": {
                "voice_id": voice_id,
                "emotion": emotion,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
            },
        }
        r = httpx.post(
            f"{BASE}/v1/t2a_v2",
            json=payload,
            headers=_headers(),
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()

        if data.get("base_resp", {}).get("status_code", -1) != 0:
            msg = data.get("base_resp", {}).get("status_msg", "ukjent feil")
            return f"MiniMax TTS feil: {msg}"

        hex_audio = data.get("data", {}).get("audio", "")
        if not hex_audio:
            return "Ingen lyd returnert fra MiniMax TTS"

        audio_bytes = bytes.fromhex(hex_audio)

        if not output_path:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            output_path = str(OUTPUT_DIR / f"tts_{int(time.time())}.mp3")

        Path(output_path).write_bytes(audio_bytes)
        duration = data.get("extra_info", {}).get("audio_length", 0)
        logger.info(f"minimax TTS: {len(text)} tegn → {output_path} ({duration:.1f}s)")
        return output_path

    except httpx.HTTPStatusError as e:
        logger.error(f"minimax TTS HTTP {e.response.status_code}: {e.response.text[:200]}")
        return f"minimax TTS HTTP {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        logger.error(f"minimax TTS feil: {e}")
        return f"minimax TTS feil: {e}"


# ── VIDEO ─────────────────────────────────────────────────────────────────────

def generate_video(
    prompt: str,
    model: str = "MiniMax-Hailuo-2.3",
    resolution: str = "1080P",
    duration: int = 6,
    image_url: Optional[str] = None,
    wait: bool = True,
    poll_interval: int = 10,
    max_wait: int = 300,
) -> dict:
    """
    Generer video fra tekst (og valgfritt bilde) med MiniMax Hailuo.

    Args:
        prompt:        Beskrivelse av videoen (maks 2000 tegn). Støtter [Pan left], [Zoom in] etc.
        model:         MiniMax-Hailuo-2.3 | MiniMax-Hailuo-02
        resolution:    720P | 1080P
        duration:      6 eller 10 sekunder
        image_url:     URL til startbilde (aktiverer image-to-video)
        wait:          Vent på ferdig resultat (poller automatisk)
        poll_interval: Sekunder mellom hver poll
        max_wait:      Maks sekunder å vente

    Returns:
        Dict med task_id, status, og video_url (hvis ferdig)
    """
    err = _check_key()
    if err:
        return {"error": err}

    try:
        payload: dict = {
            "model": model,
            "prompt": prompt[:2000],
            "duration": duration,
            "resolution": resolution,
            "prompt_optimizer": True,
        }

        endpoint = "/v1/video_generation"
        if image_url:
            payload["first_frame_image"] = image_url
            endpoint = "/v1/video_generation"  # same endpoint supports i2v with image

        r = httpx.post(
            f"{BASE}{endpoint}",
            json=payload,
            headers=_headers(),
            timeout=30,
        )
        r.raise_for_status()
        result = r.json()
        task_id = result.get("task_id") or result.get("id")

        if not task_id:
            return {"error": f"Ingen task_id returnert: {result}"}

        logger.info(f"minimax video task {task_id} startet")

        if not wait:
            return {"task_id": task_id, "status": "processing"}

        # Poll for completion
        deadline = time.time() + max_wait
        while time.time() < deadline:
            time.sleep(poll_interval)
            status = query_video_task(task_id)
            if status.get("status") in ("success", "failed"):
                return status

        return {"task_id": task_id, "status": "timeout", "error": f"Ikke ferdig etter {max_wait}s"}

    except httpx.HTTPStatusError as e:
        logger.error(f"minimax video HTTP {e.response.status_code}: {e.response.text[:200]}")
        return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        logger.error(f"minimax video feil: {e}")
        return {"error": str(e)}


def query_video_task(task_id: str) -> dict:
    """
    Sjekk status på en video-genereringsjobb.

    Returns:
        Dict med status (processing | success | failed) og video_url hvis ferdig
    """
    err = _check_key()
    if err:
        return {"error": err}
    try:
        r = httpx.get(
            f"{BASE}/v1/query/video_generation",
            params={"task_id": task_id},
            headers=_headers(),
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        return {
            "task_id": task_id,
            "status": data.get("status", "unknown"),
            "video_url": data.get("file_id") or data.get("video_url", ""),
            "raw": data,
        }
    except Exception as e:
        return {"task_id": task_id, "error": str(e)}


# ── MUSIC ─────────────────────────────────────────────────────────────────────

def generate_music(
    prompt: str,
    lyrics: Optional[str] = None,
    instrumental: bool = False,
    model: str = "music-2.5+",
    output_path: Optional[str] = None,
) -> str:
    """
    Generer musikk fra tekst og valgfrie lyrics med MiniMax.

    Args:
        prompt:       Beskriv stil, stemning, sjanger — f.eks. "upbeat lo-fi hip-hop for studying"
        lyrics:       Sangtekst med [Verse], [Chorus] etc. Kan utelates for instrumental.
        instrumental: True = kun instrumentalmusikk (uten vokal, kun music-2.5+)
        model:        music-2.5+ | music-2.5
        output_path:  Lokal filbane å lagre til. Auto-genereres hvis None.

    Returns:
        Filbane til lagret lydfil, eller feilmelding
    """
    err = _check_key()
    if err:
        return err
    if instrumental and model != "music-2.5+":
        model = "music-2.5+"  # instrumental krever music-2.5+

    try:
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "is_instrumental": instrumental,
            "stream": False,
            "output_format": "hex",
        }
        if lyrics and not instrumental:
            payload["lyrics"] = lyrics
        elif not lyrics and not instrumental:
            payload["lyrics_optimizer"] = True  # auto-generer lyrics fra prompt

        r = httpx.post(
            f"{BASE}/v1/music_generation",
            json=payload,
            headers=_headers(),
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()

        if data.get("base_resp", {}).get("status_code", -1) != 0:
            msg = data.get("base_resp", {}).get("status_msg", "ukjent feil")
            return f"MiniMax Music feil: {msg}"

        hex_audio = data.get("data", {}).get("audio", "")
        if not hex_audio:
            return "Ingen lyd returnert fra MiniMax Music"

        audio_bytes = bytes.fromhex(hex_audio)

        if not output_path:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            output_path = str(OUTPUT_DIR / f"music_{int(time.time())}.mp3")

        Path(output_path).write_bytes(audio_bytes)
        logger.info(f"minimax music generert: {output_path}")
        return output_path

    except httpx.HTTPStatusError as e:
        logger.error(f"minimax music HTTP {e.response.status_code}: {e.response.text[:200]}")
        return f"minimax music HTTP {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        logger.error(f"minimax music feil: {e}")
        return f"minimax music feil: {e}"
