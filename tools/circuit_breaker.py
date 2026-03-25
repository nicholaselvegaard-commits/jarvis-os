"""
Circuit breaker + smart retry for Jarvis.

Mønster:
  CLOSED   → normalt, kall går igjennom
  OPEN     → for mange feil, kall avvises umiddelbart
  HALF_OPEN → ett testkall tillates etter reset_timeout

Bruk:
    from tools.circuit_breaker import breaker, smart_retry

    @breaker("openai")
    def call_openai():
        ...

    @smart_retry(max_attempts=3)
    def call_with_retry():
        ...
"""
import logging
import time
import functools
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)

# ── Circuit state ──────────────────────────────────────────────────────────────

class CircuitState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-service circuit breaker."""

    def __init__(
        self,
        fail_max: int = 5,
        reset_timeout: int = 60,
        name: str = "default",
    ):
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.name = name
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._last_failure_time: float = 0

    @property
    def state(self) -> str:
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.reset_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info(f"Circuit {self.name}: OPEN → HALF_OPEN (testing)")
        return self._state

    def call(self, func: Callable, *args, **kwargs) -> Any:
        state = self.state
        if state == CircuitState.OPEN:
            raise RuntimeError(f"Circuit {self.name} is OPEN — service unavailable")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure(e)
            raise

    def _on_success(self):
        if self._state == CircuitState.HALF_OPEN:
            logger.info(f"Circuit {self.name}: HALF_OPEN → CLOSED (recovered)")
        self._failures = 0
        self._state = CircuitState.CLOSED

    def _on_failure(self, exc: Exception):
        self._failures += 1
        self._last_failure_time = time.time()
        if self._failures >= self.fail_max:
            self._state = CircuitState.OPEN
            logger.warning(f"Circuit {self.name}: CLOSED → OPEN after {self._failures} failures: {exc}")

    def is_available(self) -> bool:
        return self.state != CircuitState.OPEN

    def reset(self):
        self._failures = 0
        self._state = CircuitState.CLOSED


# ── Global registry ───────────────────────────────────────────────────────────

_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(service: str, fail_max: int = 5, reset_timeout: int = 60) -> CircuitBreaker:
    if service not in _breakers:
        _breakers[service] = CircuitBreaker(fail_max=fail_max, reset_timeout=reset_timeout, name=service)
    return _breakers[service]


def breaker(service: str, fail_max: int = 5, reset_timeout: int = 60):
    """Decorator: wrap function with circuit breaker for service."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            cb = get_breaker(service, fail_max=fail_max, reset_timeout=reset_timeout)
            return cb.call(func, *args, **kwargs)
        return wrapper
    return decorator


# ── Smart retry ───────────────────────────────────────────────────────────────

TRANSIENT_ERRORS = {
    "timeout", "connection", "network", "rate_limit", "429", "503", "502",
    "temporarily", "service unavailable", "overloaded",
}
PERMANENT_ERRORS = {
    "billing", "unauthorized", "403", "401", "invalid_api_key",
    "not found", "404", "expired", "quota exceeded",
}


def _classify_error(exc: Exception) -> str:
    """Returns 'transient' | 'permanent' | 'unknown'."""
    msg = str(exc).lower()
    if any(p in msg for p in PERMANENT_ERRORS):
        return "permanent"
    if any(p in msg for p in TRANSIENT_ERRORS):
        return "transient"
    return "unknown"


def smart_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    fallback: Optional[Callable] = None,
):
    """
    Decorator: smart retry med exponential backoff.

    - Transient errors: retry med backoff
    - Permanent errors: fail immediately, call fallback
    - Unknown: retry, then fallback
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    error_type = _classify_error(exc)

                    if error_type == "permanent":
                        logger.warning(f"{func.__name__}: permanent error, no retry: {exc}")
                        break

                    if attempt < max_attempts:
                        delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                        logger.warning(f"{func.__name__}: attempt {attempt}/{max_attempts} failed ({error_type}), retry in {delay:.1f}s: {exc}")
                        time.sleep(delay)
                    else:
                        logger.error(f"{func.__name__}: all {max_attempts} retries exhausted: {exc}")

            if fallback:
                logger.info(f"{func.__name__}: using fallback")
                return fallback(*args, **kwargs)
            raise last_exc
        return wrapper
    return decorator


def all_breakers_status() -> dict:
    """Vis status for alle circuit breakers."""
    return {name: {"state": cb.state, "failures": cb._failures} for name, cb in _breakers.items()}
