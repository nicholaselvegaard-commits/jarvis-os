"""
Revenue tracker. Aggregates MRR and ARR from Stripe, Gumroad, and manual entries.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

REVENUE_FILE = Path("memory/revenue.json")


def _load() -> dict:
    if REVENUE_FILE.exists():
        try:
            return json.loads(REVENUE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            pass
    return {"manual_mrr": {}, "history": []}


def _save(data: dict) -> None:
    REVENUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    REVENUE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def set_manual_mrr(source: str, amount_nok: float) -> None:
    """Manually set MRR for a source (e.g. a retainer customer)."""
    data = _load()
    data["manual_mrr"][source] = amount_nok
    _save(data)
    logger.info(f"Revenue: {source} = {amount_nok:,.0f} NOK/mnd")


async def get_snapshot() -> dict:
    """
    Get current revenue snapshot from all sources.

    Returns:
        Dict with mrr_nok, arr_nok, breakdown
    """
    data = _load()
    breakdown = dict(data.get("manual_mrr", {}))

    # Pull from Stripe
    try:
        from tools.stripe import get_revenue
        stripe_rev = get_revenue(months=1)
        stripe_nok = sum(v for k, v in stripe_rev.get("revenue_by_currency", {}).items() if "nok" in k.lower())
        if stripe_nok:
            breakdown["stripe"] = stripe_nok
    except Exception as exc:
        logger.warning(f"Revenue tracker: Stripe unavailable — {exc}")

    # Pull from Gumroad (USD → NOK, rough conversion)
    try:
        from tools.gumroad import get_revenue_summary
        gumroad = get_revenue_summary()
        gumroad_nok = gumroad.get("total_revenue_usd", 0) * 11  # ~11 NOK/USD
        if gumroad_nok:
            breakdown["gumroad"] = round(gumroad_nok)
    except Exception as exc:
        logger.warning(f"Revenue tracker: Gumroad unavailable — {exc}")

    total_mrr = sum(breakdown.values())
    snapshot = {
        "mrr_nok": round(total_mrr),
        "arr_nok": round(total_mrr * 12),
        "breakdown": breakdown,
        "snapshot_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }

    # Save to history
    data["history"].append(snapshot)
    data["history"] = data["history"][-24:]  # Keep 24 months
    _save(data)

    return snapshot


def format_summary(snapshot: dict) -> str:
    """Format revenue snapshot for Telegram."""
    lines = [
        f"*Revenue Snapshot — {snapshot.get('snapshot_date')}*",
        f"MRR: {snapshot.get('mrr_nok', 0):,.0f} NOK",
        f"ARR: {snapshot.get('arr_nok', 0):,.0f} NOK",
        "",
        "*Breakdown:*",
    ]
    for src, amount in snapshot.get("breakdown", {}).items():
        lines.append(f"  {src}: {amount:,.0f} NOK")
    return "\n".join(lines)
