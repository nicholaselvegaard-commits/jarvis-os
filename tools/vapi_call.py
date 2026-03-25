"""
VAPI Outbound Call Tool — Jarvis ringer hvem som helst.

Usage:
    result = make_call("+4791349949", "Hei, jeg ringer fra...")
    result = make_call("+4791349949")  # Jarvis bruker standard assistant
"""
import os
import logging
import httpx

logger = logging.getLogger(__name__)

VAPI_API_KEY     = os.getenv("VAPI_API_KEY", "")
VAPI_ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID", "")
VAPI_PHONE_NUMBER_ID = os.getenv("VAPI_PHONE_NUMBER_ID", "")


def make_call(
    to_number: str,
    first_message: str | None = None,
    assistant_overrides: dict | None = None,
) -> dict:
    """
    Ring et telefonnummer via VAPI med Jarvis sin stemme.

    Args:
        to_number: Telefonnummer med landkode, f.eks. "+4791349949"
        first_message: Første setning Jarvis sier (valgfritt)
        assistant_overrides: Dict med VAPI assistant-overrides (valgfritt)

    Returns:
        {"success": True, "call_id": "...", "status": "queued"}
        eller {"success": False, "error": "..."}
    """
    if not VAPI_API_KEY:
        return {"success": False, "error": "VAPI_API_KEY ikke satt"}
    if not VAPI_ASSISTANT_ID:
        return {"success": False, "error": "VAPI_ASSISTANT_ID ikke satt"}
    if not VAPI_PHONE_NUMBER_ID:
        return {"success": False, "error": "VAPI_PHONE_NUMBER_ID ikke satt"}

    # Normaliser nummer
    to_number = to_number.strip().replace(" ", "")
    if to_number.startswith("0047"):
        to_number = "+47" + to_number[4:]
    elif not to_number.startswith("+"):
        to_number = "+" + to_number

    payload: dict = {
        "assistantId": VAPI_ASSISTANT_ID,
        "phoneNumberId": VAPI_PHONE_NUMBER_ID,
        "customer": {"number": to_number},
    }

    if first_message or assistant_overrides:
        payload["assistantOverrides"] = assistant_overrides or {}
        if first_message:
            payload["assistantOverrides"]["firstMessage"] = first_message

    try:
        resp = httpx.post(
            "https://api.vapi.ai/call/phone",
            headers={
                "Authorization": f"Bearer {VAPI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        data = resp.json()
        if resp.status_code in (200, 201):
            logger.info(f"VAPI call queued → {to_number} | call_id={data.get('id')}")
            return {
                "success": True,
                "call_id": data.get("id"),
                "status": data.get("status", "queued"),
                "to": to_number,
            }
        else:
            logger.error(f"VAPI call failed: {data}")
            return {"success": False, "error": str(data)}
    except Exception as e:
        logger.error(f"VAPI call exception: {e}")
        return {"success": False, "error": str(e)}


def get_call_status(call_id: str) -> dict:
    """Sjekk status på en pågående eller fullført samtale."""
    try:
        resp = httpx.get(
            f"https://api.vapi.ai/call/{call_id}",
            headers={"Authorization": f"Bearer {VAPI_API_KEY}"},
            timeout=10,
        )
        data = resp.json()
        return {
            "call_id": call_id,
            "status": data.get("status"),
            "duration": data.get("endedAt"),
            "transcript": data.get("transcript", "")[:500],
            "summary": data.get("summary", ""),
        }
    except Exception as e:
        return {"error": str(e)}


def list_recent_calls(limit: int = 5) -> list:
    """Hent siste samtaler."""
    try:
        resp = httpx.get(
            "https://api.vapi.ai/call",
            headers={"Authorization": f"Bearer {VAPI_API_KEY}"},
            params={"limit": limit},
            timeout=10,
        )
        calls = resp.json()
        return [
            {
                "id": c.get("id"),
                "to": c.get("customer", {}).get("number"),
                "status": c.get("status"),
                "created": c.get("createdAt"),
                "summary": c.get("summary", "")[:200],
            }
            for c in (calls if isinstance(calls, list) else [])
        ]
    except Exception as e:
        return [{"error": str(e)}]
