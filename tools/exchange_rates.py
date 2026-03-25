"""
Fiat currency exchange rates via Norges Bank API (free, no key needed).
"""
import logging
from datetime import datetime, timezone

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)

NORGES_BANK_BASE = "https://data.norges-bank.no/api/data/EXR"


@with_retry()
def get_rates(base: str = "NOK", currencies: list[str] | None = None) -> dict[str, float]:
    """
    Get current exchange rates relative to NOK.

    Args:
        base: Base currency (NOK is default — Norges Bank's native)
        currencies: List of currency codes (None = common currencies)

    Returns:
        Dict of currency code → rate (how many NOK per 1 unit)
    """
    default_currencies = ["USD", "EUR", "GBP", "SEK", "DKK", "CHF", "JPY", "BTC"]
    targets = currencies or default_currencies

    result = {}
    for currency in targets:
        if currency == "BTC":
            result["BTC"] = _get_btc_rate()
            continue
        try:
            rate = _fetch_norges_bank(currency)
            if rate:
                result[currency] = rate
        except Exception as exc:
            logger.warning(f"Failed to fetch rate for {currency}: {exc}")

    return result


def _fetch_norges_bank(currency: str) -> float | None:
    """Fetch rate from Norges Bank for a single currency."""
    resp = httpx.get(
        f"{NORGES_BANK_BASE}/B.{currency}.NOK.SP/?lastNObservations=1&format=sdmx-json",
        timeout=10.0,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    try:
        obs = data["data"]["dataSets"][0]["series"]["0:0:0:0"]["observations"]
        latest_key = sorted(obs.keys())[-1]
        return float(obs[latest_key][0])
    except (KeyError, IndexError, ValueError):
        return None


def _get_btc_rate() -> float:
    """Get BTC/NOK rate via CoinGecko."""
    try:
        resp = httpx.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "nok"},
            timeout=5.0,
        )
        resp.raise_for_status()
        return float(resp.json()["bitcoin"]["nok"])
    except Exception:
        return 0.0


def format_rates(rates: dict[str, float]) -> str:
    """Format rates as a Telegram-friendly message."""
    lines = [f"*Valutakurser — {datetime.now(timezone.utc).strftime('%d.%m %H:%M')}*\n"]
    for currency, rate in rates.items():
        if rate:
            lines.append(f"1 {currency} = {rate:,.2f} NOK")
    return "\n".join(lines)
