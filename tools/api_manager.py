"""
API key manager. Rotates between multiple keys and tracks quota usage.
Useful when you have multiple API keys for the same service (e.g. Brave, OpenAI).
"""
import logging
import os
from collections import defaultdict
from threading import Lock

logger = logging.getLogger(__name__)

_lock = Lock()
_key_index: dict[str, int] = defaultdict(int)
_key_failures: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))

# Define key pools from env vars
# Format: SERVICE_API_KEYS=key1,key2,key3
# Fallback: SERVICE_API_KEY=key1
KEY_POOL_ENV: dict[str, str] = {
    "brave":       "BRAVE_API_KEYS",
    "openai":      "OPENAI_API_KEYS",
    "anthropic":   "ANTHROPIC_API_KEYS",
    "groq":        "GROQ_API_KEYS",
    "elevenlabs":  "ELEVENLABS_API_KEYS",
}
KEY_SINGLE_ENV: dict[str, str] = {
    "brave":       "BRAVE_API_KEY",
    "openai":      "OPENAI_API_KEY",
    "anthropic":   "ANTHROPIC_API_KEY",
    "groq":        "GROQ_API_KEY",
    "elevenlabs":  "ELEVENLABS_API_KEY",
}


def _get_keys(service: str) -> list[str]:
    """Load all keys for a service from env."""
    pool_env = KEY_POOL_ENV.get(service, "")
    pool = os.getenv(pool_env, "")
    if pool:
        return [k.strip() for k in pool.split(",") if k.strip()]
    single = os.getenv(KEY_SINGLE_ENV.get(service, ""), "")
    return [single] if single else []


def get_key(service: str) -> str:
    """
    Return the next available API key for a service (round-robin).

    Args:
        service: Service name (e.g. "brave", "openai")

    Returns:
        API key string

    Raises:
        ValueError: If no keys are configured for the service
    """
    keys = _get_keys(service)
    if not keys:
        raise ValueError(f"No API key configured for service: {service}. Check your .env file.")

    with _lock:
        idx = _key_index[service] % len(keys)
        key = keys[idx]
        _key_index[service] = (idx + 1) % len(keys)

    logger.debug(f"api_manager: {service} key #{idx + 1}/{len(keys)}")
    return key


def report_failure(service: str, key: str) -> None:
    """Report that a key failed (rate limit or auth error)."""
    keys = _get_keys(service)
    if key in keys:
        idx = keys.index(key)
        with _lock:
            _key_failures[service][idx] += 1
        logger.warning(f"api_manager: {service} key #{idx + 1} failure count = {_key_failures[service][idx]}")


def get_status() -> dict:
    """Return current key rotation status for all tracked services."""
    result = {}
    for svc in KEY_POOL_ENV:
        keys = _get_keys(svc)
        result[svc] = {
            "available_keys": len(keys),
            "current_index": _key_index.get(svc, 0),
        }
    return result
