"""
Jarvis PC Bridge — WebSocket server på Hetzner.

Tar imot screenshots fra Nicholas sin PC,
analyserer med Claude vision, sender tilbake kommandoer.

Port: 8765
"""

import asyncio
import base64
import json
import logging
import os
import time
from datetime import datetime

from dotenv import load_dotenv

load_dotenv("/opt/nexus/.env")

import websockets

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BRIDGE_TOKEN = os.getenv("PC_BRIDGE_TOKEN", "jarvis-bridge-2026")
MODEL = "claude-sonnet-4-6"

connected_clients = {}   # token → websocket
pending_tasks = {}       # task_id → asyncio.Future


async def analyze_screenshot(screenshot_b64: str, task: str, context: str = "") -> dict:
    """Claude analyserer screenshot og returnerer neste handling."""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system = """Du styrer en PC via kommandoer. Se på screenshot og bestem neste handling.

Svar med JSON:
{
  "action": "click|type|hotkey|scroll|screenshot|done|wait",
  "x": 100,          // for click (piksel fra venstre)
  "y": 200,          // for click (piksel fra topp)
  "text": "...",     // for type
  "keys": ["ctrl","c"],  // for hotkey
  "direction": "down",   // for scroll
  "ms": 1000,            // for wait
  "reason": "...",       // for done — hva ble oppnådd
  "done": false
}"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=system,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": screenshot_b64},
                },
                {
                    "type": "text",
                    "text": f"OPPGAVE: {task}\nKONTEKST: {context}\nHva er neste handling?",
                },
            ],
        }],
    )

    import re
    text = response.content[0].text
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return {"action": "done", "done": True, "reason": "Analyse feilet"}


async def handle_client(websocket):
    """Håndter en PC-klient tilkobling."""
    client_id = None
    try:
        # Autentisering
        auth_msg = await asyncio.wait_for(websocket.recv(), timeout=10)
        auth = json.loads(auth_msg)

        if auth.get("token") != BRIDGE_TOKEN:
            await websocket.send(json.dumps({"error": "Ugyldig token"}))
            return

        client_id = auth.get("client_id", f"pc-{int(time.time())}")
        connected_clients[client_id] = websocket
        logger.info(f"PC tilkoblet: {client_id}")

        await websocket.send(json.dumps({
            "type": "connected",
            "client_id": client_id,
            "message": "Jarvis PC Bridge aktiv",
        }))

        async for raw in websocket:
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "screenshot":
                    # PC sender screenshot for analyse
                    task = msg.get("task", "")
                    context = msg.get("context", "")
                    screenshot = msg.get("data", "")

                    if task and screenshot:
                        action = await analyze_screenshot(screenshot, task, context)
                        await websocket.send(json.dumps({
                            "type": "command",
                            "task_id": msg.get("task_id", ""),
                            **action,
                        }))

                elif msg_type == "result":
                    # PC rapporterer resultat av kommando
                    task_id = msg.get("task_id", "")
                    if task_id in pending_tasks:
                        pending_tasks[task_id].set_result(msg.get("data", ""))
                    logger.info(f"Resultat fra {client_id}: {str(msg.get('data',''))[:80]}")

                elif msg_type == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))

            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.error(f"Message handling feil: {e}")

    except asyncio.TimeoutError:
        logger.warning("Autentisering timeout")
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"PC frakoblet: {client_id}")
    finally:
        if client_id and client_id in connected_clients:
            del connected_clients[client_id]


async def send_task_to_pc(task: str, client_id: str = None, timeout: int = 300) -> dict:
    """
    Send en oppgave til Nicholas sin PC og vent på svar.

    Brukes fra Telegram bot: "Jarvis, åpne Chrome og gå til..."
    """
    # Finn første tilkoblede PC
    target_id = client_id or (next(iter(connected_clients)) if connected_clients else None)
    if not target_id:
        return {"success": False, "result": "Ingen PC tilkoblet. Start pc_client.py på PCen din."}

    ws = connected_clients[target_id]
    task_id = f"task-{int(time.time())}"

    # Lag Future for svar
    fut = asyncio.get_event_loop().create_future()
    pending_tasks[task_id] = fut

    # Send oppgave
    await ws.send(json.dumps({
        "type": "task",
        "task_id": task_id,
        "task": task,
        "timestamp": datetime.now().isoformat(),
    }))

    try:
        result = await asyncio.wait_for(fut, timeout=timeout)
        return {"success": True, "result": result}
    except asyncio.TimeoutError:
        return {"success": False, "result": f"Timeout etter {timeout}s"}
    finally:
        pending_tasks.pop(task_id, None)


def is_pc_connected() -> bool:
    return len(connected_clients) > 0


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    logger.info("Jarvis PC Bridge starter på port 8765...")
    async with websockets.serve(handle_client, "0.0.0.0", 8765):
        logger.info("PC Bridge klar. Venter på tilkoblinger...")
        await asyncio.Future()  # kjør for alltid


if __name__ == "__main__":
    asyncio.run(main())
