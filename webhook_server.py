"""
NEXUS Webhook Server — FastAPI.

POST /webhook/instantly   — Lead svarte paa e-post
POST /webhook/vapi        — VAPI hendelser (function-call, end-of-call-report)
GET  /health              — Helsesjekk
"""

import os
import logging
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.webhook")

app = FastAPI(title="NEXUS Webhook Server", version="2.0")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "nexus-webhook-2026")


@app.post("/webhook/instantly")
async def instantly_webhook(request: Request):
    secret = request.headers.get("x-webhook-secret", "")
    if secret and secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Ugyldig webhook secret")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Ugyldig JSON")

    event_type = data.get("event_type") or data.get("type", "unknown")
    lead_email = (
        data.get("lead", {}).get("email")
        or data.get("email")
        or data.get("to_address", "ukjent")
    )
    lead_name = (
        data.get("lead", {}).get("firstName", "")
        + " "
        + data.get("lead", {}).get("lastName", "")
    ).strip() or "Ukjent"

    logger.info(f"Instantly webhook: {event_type} fra {lead_email}")

    if event_type in ("reply_received", "REPLY"):
        await _handle_reply(data, lead_email, lead_name)
    elif event_type in ("email_opened", "OPEN"):
        await _handle_open(data, lead_email, lead_name)
    elif event_type in ("link_clicked", "CLICK"):
        await _handle_click(data, lead_email, lead_name)

    return JSONResponse({"status": "ok", "event": event_type})


async def _handle_reply(data: dict, email: str, name: str):
    reply_text = (
        data.get("reply_text")
        or data.get("body")
        or data.get("message", {}).get("body", "")
        or "(ingen tekst)"
    )
    logger.info(f"SVAR MOTTATT fra {name} ({email}): {reply_text[:100]}")
    try:
        from tools.ruflo_tool import memory_store
        memory_store(
            f"reply:{email.replace('@', '_at_')}",
            f"Navn: {name} | E-post: {email} | Svar: {reply_text[:500]} | Tid: {datetime.utcnow().isoformat()}",
        )
    except Exception as e:
        logger.error(f"Ruflo lagring feilet: {e}")
    try:
        from tools.telegram_bot import notify_owner
        notify_owner(
            f"SVAR MOTTATT!\n\nFra: {name}\nE-post: {email}\n\nMelding:\n{reply_text[:500]}"
        )
    except Exception as e:
        logger.error(f"Telegram-varsling feilet: {e}")


async def _handle_open(data: dict, email: str, name: str):
    logger.info(f"E-post aapnet: {name} ({email})")


async def _handle_click(data: dict, email: str, name: str):
    logger.info(f"Lenke klikket: {name} ({email})")
    try:
        from tools.telegram_bot import notify_owner
        notify_owner(
            f"LENKE KLIKKET\n\n{name} ({email}) klikket paa lenken i e-posten.\nHoy interesse."
        )
    except Exception as e:
        logger.error(f"Click-handling feilet: {e}")


@app.post("/webhook/vapi")
async def vapi_webhook(request: Request):
    """
    VAPI sender mange event-typer hit:
    - function-call: Jarvis vil bruke et verktoey
    - end-of-call-report: Samtalen er ferdig
    - transcript, speech-update, hang: ignorer stille
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Ugyldig JSON")

    # VAPI pakker alt under body["message"] (serverUrl-meldinger)
    msg = body.get("message", body)
    msg_type = msg.get("type", "unknown")

    logger.info(f"VAPI webhook: type={msg_type}")

    # --- Bare reager paa end-of-call-report ---
    if msg_type == "end-of-call-report":
        call = msg.get("call", {})
        artifact = msg.get("artifact", {})
        analysis = msg.get("analysis", {})

        call_id = call.get("id", "ukjent")
        ended_reason = msg.get("endedReason") or call.get("endedReason", "ukjent")
        transcript = artifact.get("transcript", "")
        summary = analysis.get("summary", "")
        outcome = analysis.get("successEvaluation", "")
        customer_name = call.get("customer", {}).get("name", "")
        customer_phone = call.get("customer", {}).get("number", "")
        duration = call.get("endedAt", "")

        # Kort Telegram-varsling
        lines = ["Samtale ferdig"]
        if customer_phone:
            lines.append(f"Nummer: {customer_phone}")
        if ended_reason and ended_reason not in ("ukjent", "customer-ended-call"):
            lines.append(f"Aarsak: {ended_reason}")
        if summary:
            lines.append(f"\n{summary[:400]}")
        elif transcript:
            lines.append(f"\nTranskript:\n{transcript[:400]}")

        try:
            from tools.telegram_bot import notify_owner
            notify_owner("\n".join(lines))
        except Exception as e:
            logger.error(f"VAPI Telegram-varsling feilet: {e}")

        # Lagre
        try:
            from tools.ruflo_tool import memory_store
            memory_store(
                f"call:{call_id}",
                f"Samtale {customer_phone} | {outcome} | {datetime.utcnow().isoformat()}\n{summary[:300]}",
            )
        except Exception as e:
            logger.error(f"VAPI Ruflo-lagring feilet: {e}")

    elif msg_type == "function-call":
        # Jarvis kalte en funksjon under samtale — haandter asynkront
        fn = msg.get("functionCall", {})
        fn_name = fn.get("name", "")
        fn_params = fn.get("parameters", {})
        logger.info(f"VAPI function-call: {fn_name}({fn_params})")
        # TODO: route til engine for faktisk utfoering
        return JSONResponse({"result": f"Utfoerer {fn_name}...", "error": None})

    # For alle andre event-typer: returner 200 stille
    return JSONResponse({"status": "ok", "type": msg_type})


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "NEXUS Webhook Server v2",
        "time": datetime.utcnow().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
