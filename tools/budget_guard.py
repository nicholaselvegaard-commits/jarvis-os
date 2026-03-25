"""
Budget guard. Raises BudgetExceededError if daily API spend exceeds the limit.
Import and call check() before any expensive API call.
"""
import logging
import os

from tools.cost_tracker import get_today_cost

logger = logging.getLogger(__name__)

DEFAULT_DAILY_BUDGET_USD = 5.00  # Sensible default — override via DAILY_BUDGET_USD env var


class BudgetExceededError(Exception):
    """Raised when the daily API budget has been exceeded."""


def get_daily_limit() -> float:
    try:
        return float(os.getenv("DAILY_BUDGET_USD", DEFAULT_DAILY_BUDGET_USD))
    except (TypeError, ValueError):
        return DEFAULT_DAILY_BUDGET_USD


def check(operation: str = "API call") -> None:
    """
    Raise BudgetExceededError if today's spend exceeds the daily limit.

    Args:
        operation: Description of the operation being attempted (for error message)
    """
    limit = get_daily_limit()
    spent = get_today_cost()
    if spent >= limit:
        msg = (
            f"Budget exceeded: ${spent:.4f} spent today (limit: ${limit:.2f}). "
            f"Blocked: {operation}. Set DAILY_BUDGET_USD env var to increase limit."
        )
        logger.error(msg)
        raise BudgetExceededError(msg)


def remaining() -> float:
    """Return remaining budget in USD for today."""
    return max(0.0, get_daily_limit() - get_today_cost())


def status() -> str:
    """Return a human-readable budget status string."""
    limit = get_daily_limit()
    spent = get_today_cost()
    pct = (spent / limit * 100) if limit > 0 else 0
    return f"Budsjett: ${spent:.4f} / ${limit:.2f} ({pct:.0f}% brukt)"
