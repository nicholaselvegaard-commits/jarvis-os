"""
NEXUS Error Handler — retry logic, backoff, and error digest.

Decorators:
    @with_retry(max_attempts=3, backoff="exponential")

Error classes handled:
    RateLimitError → wait 60s, retry
    NetworkError   → retry 3x with exponential backoff
    AuthError      → Telegram alert to Nicholas, no retry
    Unknown        → log full traceback, continue

Daily digest: collected errors saved to logs/errors.jsonl
"""
from __future__ import annotations

import json
import logging
import os
import time
import traceback
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Literal

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────

ERRORS_FILE = Path("/opt/nexus/logs/errors.jsonl")

# ── Telegram config (secrets from .env only) ─────────────────────────────────

_TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN", "")
_OWNER_CHAT_ID: str = os.getenv("TELEGRAM_OWNER_CHAT_ID", "")

# ── Internal helpers ─────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_error(record: dict[str, Any]) -> None:
    """Append one error record to errors.jsonl, creating the file if needed."""
    try:
        ERRORS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with ERRORS_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as write_exc:
        logger.error(f"error_handler: failed to write to {ERRORS_FILE}: {write_exc}")


def _send_telegram_alert(message: str) -> None:
    """
    Fire-and-forget Telegram message to the owner (Nicholas).
    Uses httpx synchronously; silently swallows send failures so an alert
    failure never causes a secondary crash.
    """
    if not _TELEGRAM_TOKEN or not _OWNER_CHAT_ID:
        logger.warning("error_handler: TELEGRAM_TOKEN / TELEGRAM_OWNER_CHAT_ID not set — skipping alert")
        return
    try:
        url = f"https://api.telegram.org/bot{_TELEGRAM_TOKEN}/sendMessage"
        with httpx.Client(timeout=10) as client:
            resp = client.post(url, json={"chat_id": _OWNER_CHAT_ID, "text": message, "parse_mode": "HTML"})
            if resp.status_code != 200:
                logger.warning(f"error_handler: Telegram alert returned {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        logger.warning(f"error_handler: Telegram alert failed: {exc}")


def _classify_http_error(exc: httpx.HTTPStatusError) -> Literal["rate_limit", "auth", "other"]:
    code = exc.response.status_code
    if code == 429:
        return "rate_limit"
    if code in (401, 403):
        return "auth"
    return "other"


def _backoff_wait(attempt: int, backoff: Literal["exponential", "linear"], cap: float = 60.0) -> float:
    """Return how many seconds to sleep before the next attempt (0-indexed attempt)."""
    if backoff == "exponential":
        return min(2 ** attempt, cap)
    # linear: 1s, 2s, 3s ...
    return min(float(attempt + 1), cap)


# ── Public decorator ─────────────────────────────────────────────────────────


def with_retry(
    max_attempts: int = 3,
    backoff: Literal["exponential", "linear"] = "exponential",
    alert_on_auth_error: bool = True,
) -> Callable:
    """
    Decorator that adds retry logic with configurable backoff.

    Behaviour per error type:
      - httpx.HTTPStatusError 429  → wait 60 s (hard), then retry
      - httpx.HTTPStatusError 401/403 → send Telegram alert to Nicholas, re-raise immediately (no retry)
      - httpx.ConnectError / httpx.TimeoutException → exponential backoff, retry
      - Any other Exception → log full traceback, exponential backoff, retry

    All errors are appended to /opt/nexus/logs/errors.jsonl.

    Args:
        max_attempts:      Total number of attempts (first try + retries).
        backoff:           "exponential" (1s, 2s, 4s…) or "linear" (1s, 2s, 3s…), capped at 60 s.
        alert_on_auth_error: Send Telegram alert to Nicholas on 401/403.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)

                except httpx.HTTPStatusError as exc:
                    error_kind = _classify_http_error(exc)
                    record = {
                        "ts": _now_iso(),
                        "func": func.__name__,
                        "attempt": attempt + 1,
                        "error_type": "HTTPStatusError",
                        "status_code": exc.response.status_code,
                        "detail": str(exc)[:400],
                    }
                    _append_error(record)

                    if error_kind == "auth":
                        msg = (
                            f"<b>NEXUS AUTH ERROR</b>\n"
                            f"Function: <code>{func.__name__}</code>\n"
                            f"Status: {exc.response.status_code}\n"
                            f"Detail: {str(exc)[:300]}"
                        )
                        if alert_on_auth_error:
                            _send_telegram_alert(msg)
                        logger.error(f"{func.__name__}: auth error {exc.response.status_code} — not retrying")
                        raise

                    if error_kind == "rate_limit":
                        wait = 60.0
                        logger.warning(
                            f"{func.__name__}: rate limited (429) — waiting {wait}s "
                            f"(attempt {attempt + 1}/{max_attempts})"
                        )
                        time.sleep(wait)
                    else:
                        # Other HTTP error — use standard backoff
                        wait = _backoff_wait(attempt, backoff)
                        logger.warning(
                            f"{func.__name__}: HTTP {exc.response.status_code} — "
                            f"waiting {wait}s (attempt {attempt + 1}/{max_attempts})"
                        )
                        time.sleep(wait)

                    last_exc = exc

                except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
                    record = {
                        "ts": _now_iso(),
                        "func": func.__name__,
                        "attempt": attempt + 1,
                        "error_type": type(exc).__name__,
                        "detail": str(exc)[:400],
                    }
                    _append_error(record)
                    wait = _backoff_wait(attempt, backoff)
                    logger.warning(
                        f"{func.__name__}: network error ({type(exc).__name__}) — "
                        f"waiting {wait}s (attempt {attempt + 1}/{max_attempts})"
                    )
                    time.sleep(wait)
                    last_exc = exc

                except Exception as exc:
                    tb = traceback.format_exc()
                    record = {
                        "ts": _now_iso(),
                        "func": func.__name__,
                        "attempt": attempt + 1,
                        "error_type": type(exc).__name__,
                        "detail": str(exc)[:400],
                        "traceback": tb[:1000],
                    }
                    _append_error(record)
                    wait = _backoff_wait(attempt, backoff)
                    logger.warning(
                        f"{func.__name__}: unknown error ({type(exc).__name__}) — "
                        f"waiting {wait}s (attempt {attempt + 1}/{max_attempts})\n{tb}"
                    )
                    time.sleep(wait)
                    last_exc = exc

            # All attempts exhausted
            logger.error(f"{func.__name__}: all {max_attempts} attempts exhausted")
            if last_exc is not None:
                raise last_exc

        return wrapper

    return decorator


# ── Digest & maintenance ─────────────────────────────────────────────────────


def get_error_digest(days: int = 1) -> str:
    """
    Read errors.jsonl and return a formatted Telegram-ready summary of errors
    from the last `days` day(s).

    Returns a plain-text / HTML summary string suitable for sending via
    _send_telegram_alert().
    """
    if not ERRORS_FILE.exists():
        return f"No errors logged in the last {days} day(s)."

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    records: list[dict[str, Any]] = []

    for line in ERRORS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            ts = datetime.fromisoformat(rec.get("ts", "1970-01-01T00:00:00+00:00"))
            if ts >= cutoff:
                records.append(rec)
        except (json.JSONDecodeError, ValueError):
            continue

    if not records:
        return f"No errors in the last {days} day(s). All systems nominal."

    # Aggregate by error_type
    by_type: dict[str, int] = {}
    by_func: dict[str, int] = {}
    for rec in records:
        etype = rec.get("error_type", "Unknown")
        fname = rec.get("func", "unknown")
        by_type[etype] = by_type.get(etype, 0) + 1
        by_func[fname] = by_func.get(fname, 0) + 1

    lines = [
        f"<b>NEXUS Error Digest — last {days}d</b>",
        f"Total errors: {len(records)}",
        "",
        "<b>By type:</b>",
    ]
    for etype, count in sorted(by_type.items(), key=lambda x: -x[1]):
        lines.append(f"  {etype}: {count}")

    lines.append("")
    lines.append("<b>By function:</b>")
    for fname, count in sorted(by_func.items(), key=lambda x: -x[1])[:10]:
        lines.append(f"  {fname}: {count}")

    # Last 3 errors for context
    lines.append("")
    lines.append("<b>Last 3 errors:</b>")
    for rec in records[-3:]:
        ts_short = rec.get("ts", "")[:19].replace("T", " ")
        lines.append(f"  [{ts_short}] {rec.get('func','?')} — {rec.get('error_type','?')}: {rec.get('detail','')[:80]}")

    return "\n".join(lines)


def clear_old_errors(days: int = 7) -> int:
    """
    Remove error records older than `days` days from errors.jsonl.

    Returns:
        Number of records removed.
    """
    if not ERRORS_FILE.exists():
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    kept: list[str] = []
    removed = 0

    for line in ERRORS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            ts = datetime.fromisoformat(rec.get("ts", "1970-01-01T00:00:00+00:00"))
            if ts >= cutoff:
                kept.append(line)
            else:
                removed += 1
        except (json.JSONDecodeError, ValueError):
            kept.append(line)  # keep unparseable lines to avoid silent data loss

    ERRORS_FILE.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    logger.info(f"error_handler: cleared {removed} error records older than {days} days")
    return removed
