"""
Vercel deployment tool. Deploy projects and get live URLs.
Requires: VERCEL_TOKEN, VERCEL_TEAM_ID (optional)
"""
import logging
import os
import time

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)

VERCEL_BASE = "https://api.vercel.com"


def _headers() -> dict:
    token = os.getenv("VERCEL_TOKEN", "")
    if not token:
        raise ValueError("VERCEL_TOKEN not set in .env")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _team_params() -> dict:
    tid = os.getenv("VERCEL_TEAM_ID", "")
    return {"teamId": tid} if tid else {}


@with_retry()
def list_projects() -> list[dict]:
    """List all Vercel projects."""
    resp = httpx.get(
        f"{VERCEL_BASE}/v9/projects",
        headers=_headers(),
        params=_team_params(),
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json().get("projects", [])


@with_retry()
def get_deployments(project_name: str, limit: int = 5) -> list[dict]:
    """Get recent deployments for a project."""
    resp = httpx.get(
        f"{VERCEL_BASE}/v6/deployments",
        headers=_headers(),
        params={"projectId": project_name, "limit": limit, **_team_params()},
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json().get("deployments", [])


@with_retry()
def trigger_deploy(project_id: str) -> dict:
    """Trigger a new deployment for a project (redeploy latest)."""
    deployments = get_deployments(project_id, limit=1)
    if not deployments:
        raise RuntimeError(f"No existing deployments found for project {project_id}")

    latest = deployments[0]
    resp = httpx.post(
        f"{VERCEL_BASE}/v13/deployments",
        headers=_headers(),
        params=_team_params(),
        json={
            "name": latest.get("name"),
            "gitSource": latest.get("gitSource"),
            "target": "production",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    logger.info(f"Vercel deploy triggered: {data.get('id')}")
    return {"id": data.get("id"), "url": f"https://{data.get('url', '')}"}


def get_project_url(project_name: str) -> str:
    """Return the current production URL for a Vercel project."""
    deployments = get_deployments(project_name, limit=1)
    if deployments:
        return f"https://{deployments[0].get('url', '')}"
    return ""
