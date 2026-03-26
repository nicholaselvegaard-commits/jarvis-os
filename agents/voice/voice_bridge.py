"""
Jarvis Voice Bridge — always-on stemme.

PC-side (voice_client.py):
- Hotword: "Jarvis" (vosk eller simpelt)
- Whisper STT: tale → tekst
- WebSocket: tekst til server, lyd tilbake

Server-side (dette):
- Tar imot tekst
- Prosesserer med Jarvis (full context)
- ElevenLabs → MP3 audio
- Sender tilbake til PC

Port: 8766
"""

import asyncio
import base64
import json
import logging
import os
import time

from dotenv import load_dotenv

load_dotenv("/opt/nexus/.env")

import websockets

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # Adam voice
BRIDGE_TOKEN = os.getenv("PC_BRIDGE_TOKEN", "jarvis-bridge-2026")

connected_voice = {}  # client_id → websocket


async def text_to_speech(text: str) -> bytes:
    """Konverter tekst til tale via ElevenLabs."""
    import httpx
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.8,
            "style": 0.0,
        },
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code == 200:
            return resp.content
        raise Exception(f"ElevenLabs feil: {resp.status_code}")


async def process_voice_input(text: str, client_id: str) -> str:
    """Prosesser tale-input med Jarvis og returner svar."""
    import sys
    sys.path.insert(0, "/opt/nexus")
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Hent brain-kontekst
    brain_ctx = ""
    try:
        from memory.brain import Brain
        b = Brain()
        brain_ctx = b.get_context(text)[:500]
    except Exception:
        pass

    try:
        from memory.smart_memory import get_context
        smart_ctx = get_context(text, max_tokens=300)
    except Exception:
        smart_ctx = ""

    system = f"""Du er Jarvis — Nicholas sin AI co-founder. Svar via stemme.

REGLER FOR STEMMESVAR:
- KORT: maks 2-3 setninger
- INGEN markdown — ren tekst
- Naturlig norsk tale
- Direkte og konkret
- Ingen "Selvfølgelig", "Flott", osv.

{f"KONTEKST: {brain_ctx}" if brain_ctx else ""}
{smart_ctx}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=system,
        messages=[{"role": "user", "content": text}],
    )
    return response.content[0].text


async def handle_voice_client(websocket):
    """Håndter en tale-klient."""
    client_id = None
    try:
        auth_msg = await asyncio.wait_for(websocket.recv(), timeout=10)
        auth = json.loads(auth_msg)

        if auth.get("token") != BRIDGE_TOKEN:
            await websocket.send(json.dumps({"error": "Ugyldig token"}))
            return

        client_id = auth.get("client_id", f"voice-{int(time.time())}")
        connected_voice[client_id] = websocket
        logger.info(f"Voice klient tilkoblet: {client_id}")

        await websocket.send(json.dumps({"type": "connected", "message": "Jarvis lytter"}))

        async for raw in websocket:
            msg = json.loads(raw)

            if msg.get("type") == "speech":
                text = msg.get("text", "").strip()
                if not text:
                    continue

                logger.info(f"Tale mottatt: {text}")

                # Prosesser med Jarvis
                reply_text = await process_voice_input(text, client_id)
                logger.info(f"Jarvis svar: {reply_text}")

                # Konverter til tale
                try:
                    audio_bytes = await text_to_speech(reply_text)
                    audio_b64 = base64.b64encode(audio_bytes).decode()
                    await websocket.send(json.dumps({
                        "type": "audio",
                        "text": reply_text,
                        "audio_b64": audio_b64,
                        "format": "mp3",
                    }))
                except Exception as e:
                    # Fallback: send bare tekst
                    await websocket.send(json.dumps({
                        "type": "text_only",
                        "text": reply_text,
                        "error": str(e),
                    }))

            elif msg.get("type") == "ping":
                await websocket.send(json.dumps({"type": "pong"}))

    except asyncio.TimeoutError:
        pass
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Voice klient frakoblet: {client_id}")
    finally:
        if client_id and client_id in connected_voice:
            del connected_voice[client_id]


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    logger.info("Jarvis Voice Bridge starter på port 8766...")
    async with websockets.serve(handle_voice_client, "0.0.0.0", 8766):
        logger.info("Voice Bridge klar.")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
