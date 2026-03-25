"""
Shared retry utility with exponential backoff.

Per CLAUDE.md spec:
  MAX_RETRIES = 3
  BACKOFF_BASE = 2  # seconds

Retry on:  network errors, timeouts, rate limits (429), 5xx
Don't retry on: auth (401/403), validation (400), not found (404)
"""
import asyncio
import logging
import time
from functools import wraps
from typing import Callable

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds

def check_http_response(resp, endpoint: str, ok: int | tuple[int, ...] = 200) -> None:
    """
    Raise the correct exception type for a non-OK HTTP response.

    Args:
        resp:     httpx Response object
        endpoint: Operation name for error messages
        ok:       Expected success status code(s), default 200
    """
    if resp.status_code in (401, 403):
        raise PermissionError(f"{endpoint}: auth failed — {resp.text[:200]}")
    ok_codes = (ok,) if isinstance(ok, int) else ok
    if resp.status_code not in ok_codes:
        raise RuntimeError(f"{endpoint} failed: {resp.status_code} — {resp.text[:200]}")


def with_retry(max_retries: int = MAX_RETRIES, backoff_base: int = BACKOFF_BASE):
    """
    Decorator that adds synchronous exponential backoff retry logic.

    Retries on:
      - Network/connection errors
      - Timeouts
      - Any RuntimeError (e.g. HTTP 429 / 5xx wrapped by callers)

    Does NOT retry on:
      - ValueError  (bad input / 400)
      - PermissionError  (auth / 401/403)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (ValueError, PermissionError):
                    raise  # Never retry these
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        wait = backoff_base ** attempt
                        logger.warning(
                            f"{func.__name__}: attempt {attempt + 1}/{max_retries} failed: {exc}. "
                            f"Retrying in {wait}s…"
                        )
                        time.sleep(wait)
                    else:
                        logger.error(f"{func.__name__}: all {max_retries} retries exhausted: {exc}")
            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator


def with_retry_async(max_retries: int = MAX_RETRIES, backoff_base: int = BACKOFF_BASE):
    """Async version of with_retry."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except (ValueError, PermissionError):
                    raise
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        wait = backoff_base ** attempt
                        logger.warning(
                            f"{func.__name__}: attempt {attempt + 1}/{max_retries} failed: {exc}. "
                            f"Retrying in {wait}s…"
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"{func.__name__}: all {max_retries} retries exhausted: {exc}")
            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator
