"""
Shared board client — Jarvis posts insights and reads MANUS messages.

The board runs on Hetzner at port 8001. MANUS connects via MCP.
Jarvis uses this module directly from agent.py and scheduler.

Usage:
    from tools.shared_board import post_insight, post_signal, get_manus_messages

Environment:
    MCP_SECRET — shared secret (same in .env and MANUS config)
    MCP_SERVER_URL — default: http://89.167.100.7:8001
"""
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MCP_URL = os.getenv("MCP_SERVER_URL", "http://89.167.100.7:8001")
MCP_SECRET = os.getenv("MCP_SECRET", "jarvis-manus-secret-2026")
HEADERS = {"x-mcp-secret": MCP_SECRET, "Content-Type": "application/json"}


def _post(endpoint: str, data: dict) -> dict:
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(f"{MCP_URL}{endpoint}", json=data, headers=HEADERS)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.error(f"shared_board._post({endpoint}) failed: {exc}")
        return {"error": str(exc)}


def _get(endpoint: str, params: dict | None = None) -> dict:
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{MCP_URL}{endpoint}", params=params, headers=HEADERS)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.error(f"shared_board._get({endpoint}) failed: {exc}")
        return {"error": str(exc)}


def post_insight(title: str, content: str, metadata: dict | None = None) -> dict:
    """Post a market insight or finding to the shared board."""
    return _post("/board", {
        "type": "insight",
        "source": "jarvis",
        "title": title,
        "content": content,
        "metadata": metadata or {},
    })


def post_signal(title: str, content: str, metadata: dict | None = None) -> dict:
    """Post a trading or opportunity signal."""
    return _post("/board", {
        "type": "signal",
        "source": "jarvis",
        "title": title,
        "content": content,
        "metadata": metadata or {},
    })


def post_task(title: str, content: str, metadata: dict | None = None) -> dict:
    """Post a task for coordination with MANUS."""
    return _post("/board", {
        "type": "task",
        "source": "jarvis",
        "title": title,
        "content": content,
        "metadata": metadata or {},
    })


def post_message(title: str, content: str) -> dict:
    """Post a direct message to MANUS."""
    return _post("/board", {
        "type": "message",
        "source": "jarvis",
        "title": title,
        "content": content,
        "metadata": {},
    })


def get_manus_messages() -> list[dict]:
    """Get unread messages from MANUS."""
    result = _get("/board/unread/jarvis")
    return result.get("entries", [])


def get_board(entry_type: str | None = None, limit: int = 20) -> list[dict]:
    """Get recent entries from the shared board."""
    params: dict[str, Any] = {"limit": limit}
    if entry_type:
        params["type"] = entry_type
    result = _get("/board", params=params)
    return result.get("entries", [])


def is_online() -> bool:
    """Check if the MCP server is reachable."""
    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{MCP_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False
