"""
Voice Tool — Vapi.ai + ElevenLabs for autonomt AI-telefonsalg.

OBLIGATORISK (Markedsføringsloven §10):
  Agenten starter ALLTID med å identifisere seg og firmaet.
"""

import os
import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)

VAPI_API_KEY = os.getenv("VAPI_API_KEY", "")
VAPI_PHONE_NUMBER_ID = os.getenv("VAPI_PHONE_NUMBER_ID", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
VAPI_BASE = "https://api.vapi.ai"

NORWEGIAN_SALES_PROMPT = """Du er NEXUS, en AI-salgsagent fra [Firmanavn] i Bodø.

OBLIGATORISK ÅPNING (aldri hopp over):
"Hei, jeg ringer fra [Firmanavn] i Bodø, jeg heter NEXUS."

MÅL: Book et 15-minutters Teams-møte for gratis AI-analyse.

SCRIPT:
1. Identifiser deg (obligatorisk per Markedsføringsloven §10)
2. Spør om du snakker med rett person
3. Forklar kort: AI-automatisering som sparer 10-20 timer/uke
4. Be om 15-minutters møte
5. Foreslå to tidspunkter

INNVENDINGER:
- "For dyrt" → "Vi starter under prisen av en deltidsansatt, ROI er umiddelbar."
- "Ikke interessert" → "Forstår. Når er det bedre å ringe tilbake?"
- "Send e-post" → "Selvfølgelig — hvilken adresse er best?"

Snakk naturlig norsk med korte pauser. Maks 3 minutter."""


def make_call(
    phone_number: str,
    customer_name: str,
    company_name: str,
    custom_prompt: Optional[str] = None,
) -> dict:
    """Ring en bedrift via Vapi.ai."""
    if not VAPI_API_KEY:
        return {"error": "VAPI_API_KEY ikke satt"}
    if not VAPI_PHONE_NUMBER_ID:
        return {"error": "VAPI_PHONE_NUMBER_ID ikke satt"}

    payload = {
        "phoneNumberId": VAPI_PHONE_NUMBER_ID,
        "customer": {"number": phone_number, "name": customer_name},
        "assistant": {
            "transcriber": {
                "provider": "deepgram",
                "language": "nb",  # Norwegian Bokmål (Deepgram kode)
            },
            "model": {
                "provider": "anthropic",
                "model": "claude-haiku-4-5-20251001",
                "messages": [{"role": "system", "content": custom_prompt or NORWEGIAN_SALES_PROMPT}],
            },
            "voice": _get_voice_config(),
            "firstMessage": (
                f"Hei, jeg ringer fra [Firmanavn] i Bodø, jeg heter NEXUS. "
                f"Snakker jeg med {customer_name}?"
            ),
            "endCallMessage": "Takk for praten! Ha en fin dag.",
            "maxDurationSeconds": 300,
        },
        "metadata": {"company": company_name, "agent": "nexus"},
    }

    headers = {"Authorization": f"Bearer {VAPI_API_KEY}", "Content-Type": "application/json"}

    try:
        resp = requests.post(f"{VAPI_BASE}/call/phone", json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"Samtale startet: {customer_name} ({phone_number}) — id: {data.get('id')}")
        return data
    except requests.exceptions.RequestException as e:
        logger.error(f"Vapi feil: {e}")
        return {"error": str(e)}


def _get_voice_config() -> dict:
    if ELEVENLABS_API_KEY:
        return {
            "provider": "11labs",
            "voiceId": os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB"),
            "stability": 0.5,
            "similarityBoost": 0.75,
        }
    return {"provider": "playht", "voiceId": "jennifer"}


def get_call_status(call_id: str) -> dict:
    if not VAPI_API_KEY:
        return {"error": "VAPI_API_KEY ikke satt"}
    try:
        resp = requests.get(
            f"{VAPI_BASE}/call/{call_id}",
            headers={"Authorization": f"Bearer {VAPI_API_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


def call_lead(lead: dict) -> dict:
    """Ring et lead fra databasen."""
    phone = lead.get("phone", "")
    if not phone:
        return {"error": "Ingen telefonnummer"}
    if not phone.startswith("+"):
        phone = f"+47{phone.lstrip('0')}"
    return make_call(
        phone_number=phone,
        customer_name=f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip(),
        company_name=lead.get("company", ""),
    )
