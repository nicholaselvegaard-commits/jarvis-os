"""
CoinGecko crypto data. Free tier — no API key required for basic use.
For higher rate limits, set COINGECKO_API_KEY.
"""
import logging
import os
from dataclasses import dataclass

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)

BASE_URL = "https://api.coingecko.com/api/v3"
PRO_BASE_URL = "https://pro-api.coingecko.com/api/v3"


def _base() -> str:
    return PRO_BASE_URL if os.getenv("COINGECKO_API_KEY") else BASE_URL


def _headers() -> dict:
    key = os.getenv("COINGECKO_API_KEY", "")
    return {"x-cg-pro-api-key": key} if key else {}


@dataclass
class CryptoPrice:
    id: str
    symbol: str
    name: str
    price_usd: float
    change_24h: float
    market_cap: float
    volume_24h: float
    rank: int


@with_retry()
def get_prices(coins: list[str]) -> list[CryptoPrice]:
    """
    Get current prices for a list of CoinGecko coin IDs.

    Args:
        coins: List of CoinGecko IDs (e.g. ['bitcoin', 'ethereum', 'solana'])

    Returns:
        List of CryptoPrice
    """
    resp = httpx.get(
        f"{_base()}/coins/markets",
        headers=_headers(),
        params={
            "vs_currency": "usd",
            "ids": ",".join(coins),
            "order": "market_cap_desc",
            "per_page": len(coins),
            "page": 1,
            "sparkline": False,
            "price_change_percentage": "24h",
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    result = []
    for c in resp.json():
        result.append(CryptoPrice(
            id=c["id"],
            symbol=c["symbol"].upper(),
            name=c["name"],
            price_usd=c.get("current_price", 0),
            change_24h=c.get("price_change_percentage_24h", 0) or 0,
            market_cap=c.get("market_cap", 0) or 0,
            volume_24h=c.get("total_volume", 0) or 0,
            rank=c.get("market_cap_rank", 0) or 0,
        ))
    return result


@with_retry()
def get_trending() -> list[dict]:
    """Return the 7 trending coins on CoinGecko right now."""
    resp = httpx.get(f"{_base()}/search/trending", headers=_headers(), timeout=10.0)
    resp.raise_for_status()
    return resp.json().get("coins", [])


@with_retry()
def get_global() -> dict:
    """Return global crypto market stats (total market cap, BTC dominance, etc.)."""
    resp = httpx.get(f"{_base()}/global", headers=_headers(), timeout=10.0)
    resp.raise_for_status()
    return resp.json().get("data", {})
