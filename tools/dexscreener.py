"""
DexScreener on-chain DEX trading data. Free, no API key needed.
Shows real-time token prices, liquidity, and volume from DEXes.
"""
import logging
from dataclasses import dataclass

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)

BASE_URL = "https://api.dexscreener.com/latest"


@dataclass
class DexPair:
    chain: str
    dex: str
    base_token: str
    quote_token: str
    price_usd: float
    price_change_24h: float
    volume_24h: float
    liquidity_usd: float
    fdv: float
    pair_address: str
    url: str


@with_retry()
def search_pairs(query: str) -> list[DexPair]:
    """
    Search for DEX pairs by token name or address.

    Args:
        query: Token name, symbol, or contract address

    Returns:
        List of DexPair (sorted by liquidity)
    """
    resp = httpx.get(f"{BASE_URL}/dex/search", params={"q": query}, timeout=10.0)
    resp.raise_for_status()
    pairs = resp.json().get("pairs", []) or []
    result = [_parse(p) for p in pairs if p.get("priceUsd")]
    result.sort(key=lambda x: x.liquidity_usd, reverse=True)
    logger.info(f"DexScreener '{query}': {len(result)} pairs")
    return result[:10]


@with_retry()
def get_pair(pair_address: str, chain: str = "solana") -> DexPair | None:
    """Get data for a specific pair address."""
    resp = httpx.get(f"{BASE_URL}/dex/pairs/{chain}/{pair_address}", timeout=10.0)
    resp.raise_for_status()
    pairs = resp.json().get("pairs", [])
    return _parse(pairs[0]) if pairs else None


@with_retry()
def get_trending() -> list[dict]:
    """Get trending tokens across all chains."""
    resp = httpx.get(f"https://api.dexscreener.com/token-boosts/top/v1", timeout=10.0)
    resp.raise_for_status()
    return resp.json()[:10] if resp.status_code == 200 else []


def _parse(p: dict) -> DexPair:
    return DexPair(
        chain=p.get("chainId", ""),
        dex=p.get("dexId", ""),
        base_token=p.get("baseToken", {}).get("symbol", ""),
        quote_token=p.get("quoteToken", {}).get("symbol", ""),
        price_usd=float(p.get("priceUsd", 0) or 0),
        price_change_24h=float((p.get("priceChange", {}) or {}).get("h24", 0) or 0),
        volume_24h=float((p.get("volume", {}) or {}).get("h24", 0) or 0),
        liquidity_usd=float((p.get("liquidity", {}) or {}).get("usd", 0) or 0),
        fdv=float(p.get("fdv", 0) or 0),
        pair_address=p.get("pairAddress", ""),
        url=p.get("url", ""),
    )
