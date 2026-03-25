"""
Resilient httpx client with retry, circuit breaker, and timeout.
Use this instead of raw httpx for all external HTTP calls.
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 2  # seconds

# Per-host circuit breaker state
_circuit_state: dict[str, dict] = {}
CIRCUIT_THRESHOLD = 5
CIRCUIT_COOLDOWN = 60  # seconds


def _get_circuit(host: str) -> dict:
    if host not in _circuit_state:
        _circuit_state[host] = {"failures": 0, "open_until": 0.0}
    return _circuit_state[host]


def _circuit_ok(host: str) -> bool:
    c = _get_circuit(host)
    if time.monotonic() < c["open_until"]:
        return False
    return True


def _record_failure(host: str) -> None:
    c = _get_circuit(host)
    c["failures"] += 1
    if c["failures"] >= CIRCUIT_THRESHOLD:
        c["open_until"] = time.monotonic() + CIRCUIT_COOLDOWN
        logger.error(f"Circuit breaker OPEN for {host} — pausing for {CIRCUIT_COOLDOWN}s")


def _record_success(host: str) -> None:
    _circuit_state[host] = {"failures": 0, "open_until": 0.0}


async def get(
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> httpx.Response:
    """Resilient async GET request."""
    return await _request("GET", url, headers=headers, params=params, timeout=timeout, max_retries=max_retries)


async def post(
    url: str,
    *,
    headers: dict | None = None,
    json: dict | None = None,
    data: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> httpx.Response:
    """Resilient async POST request."""
    return await _request("POST", url, headers=headers, json=json, data=data, timeout=timeout, max_retries=max_retries)


async def _request(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    json: dict | None = None,
    data: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> httpx.Response:
    from urllib.parse import urlparse
    host = urlparse(url).netloc

    if not _circuit_ok(host):
        raise RuntimeError(f"Circuit breaker open for {host} — skipping request")

    backoff = 1
    last_exc: Exception | None = None

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(max_retries + 1):
            try:
                resp = await client.request(
                    method, url, headers=headers, params=params, json=json, data=data
                )
                if resp.status_code == 429:
                    raise RuntimeError(f"Rate limited (429) by {host}")
                if resp.status_code >= 500:
                    raise RuntimeError(f"Server error {resp.status_code} from {host}")
                _record_success(host)
                return resp
            except (httpx.TimeoutException, httpx.ConnectError, RuntimeError) as exc:
                last_exc = exc
                _record_failure(host)
                if attempt < max_retries:
                    logger.warning(f"{method} {url}: attempt {attempt + 1} failed: {exc}. Retry in {backoff}s")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * DEFAULT_BACKOFF_BASE, 16)
                else:
                    logger.error(f"{method} {url}: all {max_retries} retries exhausted")

    raise last_exc  # type: ignore[misc]
