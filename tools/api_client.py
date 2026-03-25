"""Generic API client with retry and auth handling."""
import logging
import time
from typing import Any, Optional
import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 2
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class APIResponse(BaseModel):
    status_code: int
    data: Any
    headers: dict


def request(
    method: str,
    url: str,
    *,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    json: Optional[dict] = None,
    bearer_token: Optional[str] = None,
    timeout: int = 30,
) -> APIResponse:
    """
    Make an HTTP request with retry logic and auth support.

    Args:
        method: HTTP method (GET, POST, etc.).
        url: Full URL.
        headers: Optional request headers.
        params: Optional query parameters.
        json: Optional JSON body.
        bearer_token: If provided, adds Authorization: Bearer header.
        timeout: Request timeout in seconds.

    Returns:
        APIResponse with status code and parsed data.
    """
    all_headers = headers or {}
    if bearer_token:
        all_headers["Authorization"] = f"Bearer {bearer_token}"

    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.request(
                    method.upper(),
                    url,
                    headers=all_headers,
                    params=params,
                    json=json,
                )

            if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                wait = BACKOFF_BASE ** attempt
                logger.warning(f"Got {response.status_code}, retrying in {wait}s (attempt {attempt})")
                time.sleep(wait)
                continue

            response.raise_for_status()

            try:
                data = response.json()
            except Exception:
                data = response.text

            return APIResponse(
                status_code=response.status_code,
                data=data,
                headers=dict(response.headers),
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"API error {e.response.status_code}: {url}")
            raise
        except httpx.RequestError as e:
            last_error = e
            if attempt < MAX_RETRIES:
                wait = BACKOFF_BASE ** attempt
                logger.warning(f"Request error, retrying in {wait}s: {e}")
                time.sleep(wait)
            else:
                logger.error(f"Request failed after {MAX_RETRIES} attempts: {e}")
                raise

    raise RuntimeError(f"API request failed: {url}") from last_error
