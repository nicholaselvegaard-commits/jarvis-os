"""
Make.com (Integromat) client — create and manage automation scenarios.

Jarvis can autonomously create workflows that run 24/7 without a server.
Use this to: send notifications, process data, connect apps, run at schedules.

Usage:
    from tools.make_client import list_scenarios, trigger_webhook, create_scenario
"""
import logging
import os
import httpx

logger = logging.getLogger(__name__)

MAKE_API_KEY = os.getenv("MAKE_API_KEY", "")
BASE_URL = "https://eu1.make.com/api/v2"  # or us1 depending on account region


def _headers() -> dict:
    return {
        "Authorization": f"Token {MAKE_API_KEY}",
        "Content-Type": "application/json",
    }


def list_scenarios() -> list[dict]:
    """List all Make.com scenarios in the account."""
    if not MAKE_API_KEY:
        raise ValueError("MAKE_API_KEY not set in .env")
    with httpx.Client(timeout=15) as client:
        r = client.get(f"{BASE_URL}/scenarios", headers=_headers())
        r.raise_for_status()
        data = r.json()
    scenarios = data.get("scenarios", [])
    logger.info(f"Make.com: {len(scenarios)} scenarios found")
    return scenarios


def trigger_webhook(webhook_url: str, payload: dict) -> dict:
    """
    Trigger a Make.com webhook with a custom payload.
    The webhook URL is found in the scenario's webhook module.
    """
    with httpx.Client(timeout=15) as client:
        r = client.post(webhook_url, json=payload)
        r.raise_for_status()
    logger.info(f"Make.com webhook triggered: {webhook_url[:50]}")
    return {"status": "triggered", "url": webhook_url}


def get_scenario(scenario_id: int) -> dict:
    """Get details about a specific scenario."""
    if not MAKE_API_KEY:
        raise ValueError("MAKE_API_KEY not set in .env")
    with httpx.Client(timeout=15) as client:
        r = client.get(f"{BASE_URL}/scenarios/{scenario_id}", headers=_headers())
        r.raise_for_status()
        return r.json().get("scenario", {})


def activate_scenario(scenario_id: int) -> dict:
    """Activate (enable) a scenario."""
    if not MAKE_API_KEY:
        raise ValueError("MAKE_API_KEY not set in .env")
    with httpx.Client(timeout=15) as client:
        r = client.patch(
            f"{BASE_URL}/scenarios/{scenario_id}",
            headers=_headers(),
            json={"isEnabled": True},
        )
        r.raise_for_status()
        return {"status": "activated", "id": scenario_id}


def deactivate_scenario(scenario_id: int) -> dict:
    """Deactivate (pause) a scenario."""
    if not MAKE_API_KEY:
        raise ValueError("MAKE_API_KEY not set in .env")
    with httpx.Client(timeout=15) as client:
        r = client.patch(
            f"{BASE_URL}/scenarios/{scenario_id}",
            headers=_headers(),
            json={"isEnabled": False},
        )
        r.raise_for_status()
        return {"status": "deactivated", "id": scenario_id}


def get_executions(scenario_id: int, limit: int = 10) -> list[dict]:
    """Get recent execution history for a scenario."""
    if not MAKE_API_KEY:
        raise ValueError("MAKE_API_KEY not set in .env")
    with httpx.Client(timeout=15) as client:
        r = client.get(
            f"{BASE_URL}/scenarios/{scenario_id}/logs",
            headers=_headers(),
            params={"pg[limit]": limit},
        )
        r.raise_for_status()
        return r.json().get("scenarioLogs", [])
