"""
API cost tracking. Logs token usage and estimates cost per call.
Persists daily totals to memory/cost_log.json.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

COST_LOG_FILE = Path("memory/cost_log.json")

# Prices per 1M tokens (USD) — update as pricing changes
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-6":           {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6":         {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.25,  "output": 1.25},
    "gpt-4o":                    {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":               {"input": 0.15,  "output": 0.60},
    "groq/llama-3.3-70b":        {"input": 0.00,  "output": 0.00},
    "gemini-2.0-flash":          {"input": 0.10,  "output": 0.40},
}


def _load_log() -> dict:
    if COST_LOG_FILE.exists():
        try:
            return json.loads(COST_LOG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            pass
    return {"daily": {}, "total_usd": 0.0}


def _save_log(log: dict) -> None:
    COST_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    COST_LOG_FILE.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")


def record_usage(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Record token usage and return cost in USD.

    Args:
        model: Model name/ID
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens generated

    Returns:
        Estimated cost in USD
    """
    pricing = MODEL_PRICING.get(model, {"input": 3.00, "output": 15.00})
    cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log = _load_log()

    if today not in log["daily"]:
        log["daily"][today] = {"cost_usd": 0.0, "calls": 0, "tokens": 0}

    log["daily"][today]["cost_usd"] += cost
    log["daily"][today]["calls"] += 1
    log["daily"][today]["tokens"] += input_tokens + output_tokens
    log["total_usd"] += cost

    _save_log(log)
    logger.debug(f"Cost: ${cost:.4f} ({model}, {input_tokens}+{output_tokens} tokens)")
    return cost


def get_today_cost() -> float:
    """Return today's total API spend in USD."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log = _load_log()
    return log.get("daily", {}).get(today, {}).get("cost_usd", 0.0)


def get_total_cost() -> float:
    """Return all-time total API spend in USD."""
    return _load_log().get("total_usd", 0.0)


def get_summary() -> str:
    """Return a human-readable cost summary."""
    log = _load_log()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_cost = log.get("daily", {}).get(today, {}).get("cost_usd", 0.0)
    total = log.get("total_usd", 0.0)
    return f"Dagens kostnad: ${today_cost:.4f} | Totalt: ${total:.2f}"
