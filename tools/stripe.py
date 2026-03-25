"""
Stripe integration for payment management.

Required env vars:
  STRIPE_SECRET_KEY — sk_live_... or sk_test_... (test key recommended for dev)

Dependencies: httpx (already in requirements.txt)
"""
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

from tools.retry import check_http_response, with_retry

load_dotenv()

logger = logging.getLogger(__name__)

STRIPE_BASE = "https://api.stripe.com/v1"


def _headers() -> dict:
    api_key = os.getenv("STRIPE_SECRET_KEY")
    if not api_key:
        raise ValueError("STRIPE_SECRET_KEY must be set in .env")
    return {"Authorization": f"Bearer {api_key}"}


@with_retry()
def get_balance() -> dict:
    """
    Get current Stripe account balance.

    Returns:
        Dict with 'available' and 'pending' — amounts per currency (in major units, e.g. NOK)
    """
    resp = httpx.get(f"{STRIPE_BASE}/balance", headers=_headers(), timeout=30)
    check_http_response(resp, "get_balance")

    data = resp.json()
    result = {
        "available": {a["currency"].upper(): a["amount"] / 100 for a in data.get("available", [])},
        "pending": {p["currency"].upper(): p["amount"] / 100 for p in data.get("pending", [])},
    }
    logger.info(f"Stripe balance: {result}")
    return result


@with_retry()
def list_payments(limit: int = 10) -> list[dict]:
    """
    List recent payment intents.

    Args:
        limit: Number of payments (default 10, max 100)

    Returns:
        List of dicts: id, amount, currency, status, description, created (unix ts)
    """
    resp = httpx.get(
        f"{STRIPE_BASE}/payment_intents",
        headers=_headers(),
        params={"limit": min(limit, 100)},
        timeout=30,
    )
    check_http_response(resp, "list_payments")

    payments = [
        {
            "id": pi["id"],
            "amount": pi["amount"] / 100,
            "currency": pi["currency"].upper(),
            "status": pi["status"],
            "customer": pi.get("customer") or "",
            "description": pi.get("description") or "",
            "created": pi.get("created", 0),
        }
        for pi in resp.json().get("data", [])
    ]
    logger.info(f"Stripe: fetched {len(payments)} payment intents")
    return payments


@with_retry()
def create_payment_link(
    amount_cents: int,
    currency: str,
    product_name: str,
    quantity: int = 1,
) -> dict:
    """
    Create a Stripe payment link (product → price → link).

    Args:
        amount_cents: Amount in smallest currency unit (e.g. 250000 = 2500 NOK)
        currency: ISO currency code, e.g. 'nok', 'usd', 'eur'
        product_name: What the customer sees (e.g. 'Nettside — Bodø Pizzeria')
        quantity: Number of items (default 1)

    Returns:
        Dict: id, url
    """
    h = _headers()

    product_resp = httpx.post(f"{STRIPE_BASE}/products", headers=h, data={"name": product_name}, timeout=30)
    check_http_response(product_resp, "create product")
    product_id = product_resp.json()["id"]

    price_resp = httpx.post(
        f"{STRIPE_BASE}/prices",
        headers=h,
        data={"product": product_id, "unit_amount": str(amount_cents), "currency": currency.lower()},
        timeout=30,
    )
    check_http_response(price_resp, "create price")
    price_id = price_resp.json()["id"]

    link_resp = httpx.post(
        f"{STRIPE_BASE}/payment_links",
        headers=h,
        data={"line_items[0][price]": price_id, "line_items[0][quantity]": str(quantity)},
        timeout=30,
    )
    check_http_response(link_resp, "create_payment_link", ok=(200, 201))

    data = link_resp.json()
    logger.info(f"Stripe: payment link created — {data['url']}")
    return {"id": data["id"], "url": data["url"]}


@with_retry()
def get_revenue(months: int = 1) -> dict:
    """
    Calculate total succeeded revenue for recent months.

    Args:
        months: How many months back to look (default 1)

    Returns:
        Dict: revenue_by_currency (e.g. {'NOK': 7500.0}), payment_count
    """
    since = int((datetime.now(timezone.utc) - timedelta(days=30 * months)).timestamp())

    resp = httpx.get(
        f"{STRIPE_BASE}/charges",
        headers=_headers(),
        params={"limit": 100, "created[gte]": since},
        timeout=30,
    )
    check_http_response(resp, "get_revenue")

    by_currency: dict[str, float] = {}
    count = 0
    for charge in resp.json().get("data", []):
        if charge.get("status") == "succeeded":
            currency = charge["currency"].upper()
            by_currency[currency] = by_currency.get(currency, 0) + charge["amount"] / 100
            count += 1

    logger.info(f"Stripe: {months}-month revenue: {by_currency} ({count} charges)")
    return {"revenue_by_currency": by_currency, "payment_count": count}
