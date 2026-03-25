"""
FinanceAgent — Financial intelligence: crypto prices, revenue tracking, burn rate.

Fetches live NOK prices from CoinGecko, alerts on >5% 24h moves,
cross-references daily revenue vs API burn rate, and notifies Nicholas
when action is needed.
"""

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from agents.jordan.tools.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# CoinGecko — free tier, no key required for basic use
_COINGECKO_MARKETS_URL = (
    "https://api.coingecko.com/api/v3/coins/markets"
    "?vs_currency=nok"
    "&ids=bitcoin,ethereum,solana"
    "&order=market_cap_desc"
    "&price_change_percentage=24h"
)

# Estimated daily API spend in USD (Anthropic + Groq)
_DAILY_BURN_USD = 15.0

# Approximate USD → NOK exchange rate (static fallback; ideally from env/tool)
_USD_TO_NOK = 11.0

# 24h price change threshold that triggers a Telegram alert
_ALERT_THRESHOLD_PCT = 5.0

_SYSTEM = """\
You are FinanceAgent — a sharp financial analyst embedded in the NEXUS system.
Your role: monitor crypto volatility, track daily revenue vs burn rate, and flag
when Nicholas needs to act. Be direct and data-driven. No fluff.
"""


def _fetch_crypto_nok() -> list[dict[str, Any]]:
    """
    Fetch BTC, ETH, SOL prices and 24h % change in NOK from CoinGecko /coins/markets.

    Returns a list of dicts with keys:
        id, symbol, current_price_nok, price_change_pct_24h
    """
    try:
        resp = httpx.get(_COINGECKO_MARKETS_URL, timeout=15.0)
        resp.raise_for_status()
        coins = []
        for item in resp.json():
            coins.append({
                "id": item.get("id", ""),
                "symbol": item.get("symbol", "").upper(),
                "current_price_nok": item.get("current_price", 0) or 0,
                "price_change_pct_24h": (
                    item.get("price_change_percentage_24h_in_currency")
                    or item.get("price_change_percentage_24h")
                    or 0
                ),
            })
        return coins
    except Exception as exc:
        logger.error(f"FinanceAgent: CoinGecko fetch failed: {exc}")
        return []


def _build_report(
    coins: list[dict[str, Any]],
    total_revenue_nok: float,
    daily_revenue_nok: float,
    burn_nok: float,
    alerts: list[str],
) -> str:
    """Compose the plain-text finance report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"FinanceAgent Report — {now}", ""]

    # Crypto section
    lines.append("CRYPTO (NOK):")
    for coin in coins:
        change = coin["price_change_pct_24h"]
        arrow = "^" if change >= 0 else "v"
        lines.append(
            f"  {coin['symbol']:4s}  {coin['current_price_nok']:>12,.2f} NOK  "
            f"({arrow}{abs(change):.1f}% 24h)"
        )

    lines.append("")

    # Revenue section
    daily_net_nok = daily_revenue_nok - burn_nok
    lines.append("REVENUE TODAY:")
    lines.append(f"  Earned:    {daily_revenue_nok:>10,.2f} NOK")
    lines.append(f"  Burn rate: {burn_nok:>10,.2f} NOK/day  (~${_DAILY_BURN_USD}/day)")
    lines.append(f"  Net:       {daily_net_nok:>10,.2f} NOK  {'(positive)' if daily_net_nok >= 0 else '(LOSS)'}")
    lines.append(f"  Total:     {total_revenue_nok:>10,.2f} NOK")

    if alerts:
        lines.append("")
        lines.append("ALERTS:")
        for alert in alerts:
            lines.append(f"  ! {alert}")

    return "\n".join(lines)


class FinanceAgent(BaseAgent):
    """Crypto + revenue intelligence. Alerts on >5% moves and daily P&L."""

    name = "finance"
    system_prompt = _SYSTEM
    max_tokens = 512

    async def _act(self, task: str, plan: str) -> str:
        # ── 1. Fetch crypto prices in NOK ─────────────────────────────────────
        coins = _fetch_crypto_nok()

        # ── 2. Detect >5% 24h moves ──────────────────────────────────────────
        alerts: list[str] = []
        for coin in coins:
            pct = coin["price_change_pct_24h"]
            if abs(pct) > _ALERT_THRESHOLD_PCT:
                direction = "UP" if pct > 0 else "DOWN"
                alerts.append(
                    f"{coin['symbol']} moved {direction} {abs(pct):.1f}% in 24h "
                    f"(now {coin['current_price_nok']:,.0f} NOK)"
                )

        # ── 3. Revenue and burn rate ──────────────────────────────────────────
        total_revenue_nok: float = 0.0
        daily_revenue_nok: float = 0.0
        try:
            from memory.goals import get_total_revenue, get_daily_revenue
            total_revenue_nok = get_total_revenue()
            daily_revenue_nok = get_daily_revenue()
        except Exception as exc:
            logger.warning(f"FinanceAgent: could not read revenue: {exc}")

        burn_nok = _DAILY_BURN_USD * _USD_TO_NOK

        # Alert if today's revenue exceeds zero (useful event, not just zero check)
        if daily_revenue_nok > 0:
            alerts.append(
                f"Revenue today: {daily_revenue_nok:,.2f} NOK "
                f"(net after burn: {daily_revenue_nok - burn_nok:,.2f} NOK)"
            )

        # ── 4. Build report ───────────────────────────────────────────────────
        report = _build_report(
            coins=coins,
            total_revenue_nok=total_revenue_nok,
            daily_revenue_nok=daily_revenue_nok,
            burn_nok=burn_nok,
            alerts=alerts,
        )

        # ── 5. Notify via Telegram if there are alerts or daily revenue > 0 ──
        should_notify = bool(alerts)
        if should_notify:
            try:
                from telegram_bot import notify_owner
                notify_owner(f"FinanceAgent\n\n{report}")
                logger.info("FinanceAgent: Telegram alert sent")
            except Exception as exc:
                logger.error(f"FinanceAgent: Telegram notify failed: {exc}")

        logger.info(f"FinanceAgent: done. Alerts: {len(alerts)}, revenue today: {daily_revenue_nok:.2f} NOK")
        return report
