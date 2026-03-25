"""
Health monitor. Checks connectivity to all external services.
Returns a status dict and can send Telegram alerts on failures.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

SERVICES = {
    "anthropic":   "https://api.anthropic.com",
    "openai":      "https://api.openai.com",
    "groq":        "https://api.groq.com",
    "telegram":    "https://api.telegram.org",
    "brave":       "https://api.search.brave.com",
    "github":      "https://api.github.com",
    "google":      "https://www.googleapis.com",
    "stripe":      "https://api.stripe.com",
    "elevenlabs":  "https://api.elevenlabs.io",
    "openrouter":  "https://openrouter.ai",
}


async def _check_service(name: str, url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.head(url)
            ok = resp.status_code < 500
            return {"service": name, "status": "ok" if ok else "degraded", "code": resp.status_code}
    except Exception as exc:
        return {"service": name, "status": "down", "error": str(exc)[:100]}


async def check_all() -> list[dict]:
    """Check all services concurrently. Returns list of status dicts."""
    tasks = [_check_service(name, url) for name, url in SERVICES.items()]
    results = await asyncio.gather(*tasks)
    return list(results)


async def get_summary() -> str:
    """Return a human-readable health summary string."""
    results = await check_all()
    ok = [r["service"] for r in results if r["status"] == "ok"]
    down = [r["service"] for r in results if r["status"] == "down"]
    degraded = [r["service"] for r in results if r["status"] == "degraded"]

    lines = [f"Health check — {datetime.now(timezone.utc).strftime('%H:%M UTC')}"]
    if ok:
        lines.append(f"OK ({len(ok)}): {', '.join(ok)}")
    if degraded:
        lines.append(f"Degraded: {', '.join(degraded)}")
    if down:
        lines.append(f"DOWN: {', '.join(down)}")
    return "\n".join(lines)
