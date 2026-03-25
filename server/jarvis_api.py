"""
Jarvis REST API — eksponerer Jarvis sine evner til MANUS og andre systemer.

Endepunkter:
  POST /task          — gi Jarvis en oppgave, få task_id tilbake
  GET  /task/{id}     — sjekk status på oppgave
  POST /approve       — Nicholas godkjenner noe (e-post, utgift, handling)
  GET  /status        — hva Jarvis jobber med nå
  GET  /health        — helsesjekk
  GET  /metrics       — inntekt, leads, e-poster i dag

Auth: Bearer token i Authorization-header (JARVIS_API_TOKEN fra .env)

Bruk: MANUS-boten, Make.com, Nicholas sin telefon
Port: 8082
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jarvis.api")

API_TOKEN = os.getenv("JARVIS_API_TOKEN", "jarvis-api-2026")
TASKS_FILE = Path("/opt/nexus/memory/api_tasks.json")
PENDING_FILE = Path("/opt/nexus/memory/pending_approvals.json")

app = FastAPI(
    title="Jarvis API",
    description="REST API for Jarvis — MANUS integration, task queue, approval system",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)


# ── Auth ──────────────────────────────────────────────────────────────────────

def _verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if not credentials or credentials.credentials != API_TOKEN:
        raise HTTPException(status_code=401, detail="Ugyldig API-token")
    return credentials.credentials


# ── Storage helpers ───────────────────────────────────────────────────────────

def _load_tasks() -> dict:
    if TASKS_FILE.exists():
        try:
            return json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_tasks(tasks: dict) -> None:
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_pending() -> dict:
    if PENDING_FILE.exists():
        try:
            return json.loads(PENDING_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_pending(pending: dict) -> None:
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_FILE.write_text(json.dumps(pending, indent=2, ensure_ascii=False), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Models ────────────────────────────────────────────────────────────────────

class TaskRequest(BaseModel):
    task: str
    source: str = "api"           # "manus" | "nicholas" | "api"
    priority: int = 1             # 1=normal, 2=høy, 3=kritisk
    context: Optional[dict] = None


class ApproveRequest(BaseModel):
    approval_id: str
    approved: bool
    note: Optional[str] = None


# ── Background task runner ────────────────────────────────────────────────────

def _run_task_background(task_id: str, task_text: str, source: str):
    """Kjør oppgaven via Jarvis engine og oppdater status."""
    tasks = _load_tasks()
    tasks[task_id]["status"] = "running"
    _save_tasks(tasks)

    try:
        # Prøv å kjøre via engine hvis tilgjengelig
        import sys
        sys.path.insert(0, "/opt/nexus")
        from core.engine import run as process_message

        import asyncio
        result = asyncio.run(
            process_message(
                user_message=task_text,
                chat_id=f"api_{task_id}",
                telegram_send=lambda *a, **k: None,  # No Telegram for API tasks
            )
        )
        tasks = _load_tasks()
        tasks[task_id]["status"] = "done"
        tasks[task_id]["result"] = str(result)[:2000]
        tasks[task_id]["finished_at"] = _now()

    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        tasks = _load_tasks()
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)
        tasks[task_id]["finished_at"] = _now()

    _save_tasks(tasks)
    logger.info(f"Task {task_id} done: {tasks[task_id]['status']}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/task", dependencies=[Depends(_verify_token)])
async def create_task(req: TaskRequest, background_tasks: BackgroundTasks):
    """
    Gi Jarvis en oppgave. Kjøres asynkront.

    Returns: {task_id, status, message}
    """
    task_id = str(uuid.uuid4())[:8]
    tasks = _load_tasks()
    tasks[task_id] = {
        "id": task_id,
        "task": req.task,
        "source": req.source,
        "priority": req.priority,
        "context": req.context or {},
        "status": "queued",
        "result": None,
        "error": None,
        "created_at": _now(),
        "finished_at": None,
    }
    _save_tasks(tasks)

    background_tasks.add_task(_run_task_background, task_id, req.task, req.source)

    logger.info(f"Task {task_id} queued: {req.task[:80]} (fra {req.source})")

    return {
        "task_id": task_id,
        "status": "queued",
        "message": f"Oppgave mottatt. Poll GET /task/{task_id} for status.",
    }


@app.get("/task/{task_id}", dependencies=[Depends(_verify_token)])
async def get_task(task_id: str):
    """Sjekk status på en oppgave."""
    tasks = _load_tasks()
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} ikke funnet")
    return tasks[task_id]


@app.get("/tasks", dependencies=[Depends(_verify_token)])
async def list_tasks(limit: int = 20, status: Optional[str] = None):
    """List alle oppgaver, nyeste først."""
    tasks = _load_tasks()
    items = sorted(tasks.values(), key=lambda x: x["created_at"], reverse=True)
    if status:
        items = [t for t in items if t["status"] == status]
    return {"tasks": items[:limit], "total": len(tasks)}


@app.post("/approve", dependencies=[Depends(_verify_token)])
async def approve_action(req: ApproveRequest):
    """
    Nicholas godkjenner eller avviser en ventende handling.
    Brukes for: utgifter >200kr, e-poster fra Gmail, destruktive handlinger.
    """
    pending = _load_pending()
    if req.approval_id not in pending:
        raise HTTPException(status_code=404, detail=f"Ingen ventende godkjenning med ID {req.approval_id}")

    item = pending[req.approval_id]
    item["approved"] = req.approved
    item["note"] = req.note or ""
    item["resolved_at"] = _now()
    item["status"] = "approved" if req.approved else "rejected"

    pending[req.approval_id] = item
    _save_pending(pending)

    # Notify Jarvis via smart_memory
    try:
        from memory.smart_memory import save
        verdict = "GODKJENT" if req.approved else "AVVIST"
        save("task", f"Godkjenning {verdict}: {item.get('description','?')} | Note: {req.note or '-'}", priority=2)
    except Exception:
        pass

    logger.info(f"Approval {req.approval_id}: {'godkjent' if req.approved else 'avvist'}")
    return {
        "approval_id": req.approval_id,
        "status": item["status"],
        "description": item.get("description", ""),
    }


@app.get("/approvals/pending", dependencies=[Depends(_verify_token)])
async def list_pending_approvals():
    """List alle ventende godkjenninger."""
    pending = _load_pending()
    items = [v for v in pending.values() if v.get("status") == "waiting"]
    return {"pending": items, "count": len(items)}


@app.get("/status")
async def get_status():
    """Hva jobber Jarvis med nå — public endpoint."""
    tasks = _load_tasks()
    running = [t for t in tasks.values() if t["status"] == "running"]
    queued = [t for t in tasks.values() if t["status"] == "queued"]
    recent_done = sorted(
        [t for t in tasks.values() if t["status"] == "done"],
        key=lambda x: x.get("finished_at", ""),
        reverse=True,
    )[:5]

    return {
        "status": "active",
        "running": len(running),
        "queued": len(queued),
        "current_task": running[0]["task"][:100] if running else None,
        "recent_completed": [{"id": t["id"], "task": t["task"][:80]} for t in recent_done],
    }


@app.get("/metrics", dependencies=[Depends(_verify_token)])
async def get_metrics():
    """Inntekt, leads og e-poster i dag."""
    metrics = {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "generated_at": _now(),
    }
    try:
        from memory.goals import get_daily_revenue, get_total_revenue
        metrics["revenue_today_nok"] = get_daily_revenue()
        metrics["revenue_total_nok"] = get_total_revenue()
    except Exception:
        metrics["revenue_today_nok"] = 0
        metrics["revenue_total_nok"] = 0

    try:
        from memory.smart_memory import stats
        metrics["memory_stats"] = stats()
    except Exception:
        pass

    return metrics


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "Jarvis API v1.0",
        "time": _now(),
        "docs": "/docs",
    }


# ── MANUS-specific endpoint ───────────────────────────────────────────────────

@app.post("/manus/message", dependencies=[Depends(_verify_token)])
async def manus_message(req: TaskRequest, background_tasks: BackgroundTasks):
    """
    MANUS sender en melding til Jarvis.
    Samme som /task men logget som MANUS-kilde.
    """
    req.source = "manus"
    return await create_task(req, background_tasks)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082, log_level="info")
