"""
Supabase client. Database, auth, and storage for the agent platform.
Requires: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import logging
import os

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)


def _base_url() -> str:
    url = os.getenv("SUPABASE_URL", "")
    if not url:
        raise ValueError("SUPABASE_URL not set in .env")
    return url.rstrip("/")


def _headers(use_service_role: bool = True) -> dict:
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY" if use_service_role else "SUPABASE_ANON_KEY", "")
    if not key:
        raise ValueError("SUPABASE_SERVICE_ROLE_KEY not set in .env")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


@with_retry()
def select(table: str, filters: dict | None = None, limit: int = 100) -> list[dict]:
    """
    Query rows from a Supabase table.

    Args:
        table: Table name
        filters: Dict of column=value equality filters
        limit: Max rows

    Returns:
        List of row dicts
    """
    params: dict = {"limit": limit}
    if filters:
        params.update(filters)

    resp = httpx.get(
        f"{_base_url()}/rest/v1/{table}",
        headers=_headers(),
        params=params,
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


@with_retry()
def insert(table: str, data: dict | list[dict]) -> list[dict]:
    """Insert one or more rows into a Supabase table."""
    rows = data if isinstance(data, list) else [data]
    resp = httpx.post(
        f"{_base_url()}/rest/v1/{table}",
        headers=_headers(),
        json=rows,
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


@with_retry()
def update(table: str, filters: dict, data: dict) -> list[dict]:
    """Update rows matching filters."""
    params = {k: f"eq.{v}" for k, v in filters.items()}
    resp = httpx.patch(
        f"{_base_url()}/rest/v1/{table}",
        headers=_headers(),
        params=params,
        json=data,
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


@with_retry()
def delete(table: str, filters: dict) -> None:
    """Delete rows matching filters."""
    params = {k: f"eq.{v}" for k, v in filters.items()}
    resp = httpx.delete(
        f"{_base_url()}/rest/v1/{table}",
        headers=_headers(),
        params=params,
        timeout=15.0,
    )
    resp.raise_for_status()


@with_retry()
def rpc(function_name: str, params: dict | None = None) -> dict:
    """Call a Supabase Edge Function or database RPC."""
    resp = httpx.post(
        f"{_base_url()}/rest/v1/rpc/{function_name}",
        headers=_headers(),
        json=params or {},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()
