"""
Gumroad API client. Manage digital products, sales, and subscribers.
Requires: GUMROAD_ACCESS_TOKEN
"""
import logging
import os
from dataclasses import dataclass

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)

GUMROAD_BASE = "https://api.gumroad.com/v2"


def _headers() -> dict:
    token = os.getenv("GUMROAD_ACCESS_TOKEN", "")
    if not token:
        raise ValueError("GUMROAD_ACCESS_TOKEN not set in .env")
    return {"Authorization": f"Bearer {token}"}


@with_retry()
def list_products() -> list[dict]:
    """List all products on the Gumroad account."""
    resp = httpx.get(f"{GUMROAD_BASE}/products", headers=_headers(), timeout=10.0)
    resp.raise_for_status()
    return resp.json().get("products", [])


@with_retry()
def get_sales(product_id: str | None = None, after: str | None = None) -> list[dict]:
    """
    Get sales data.

    Args:
        product_id: Filter by specific product (None = all)
        after: ISO date string to filter sales after this date

    Returns:
        List of sale dicts
    """
    params: dict = {}
    if product_id:
        params["product_id"] = product_id
    if after:
        params["after"] = after

    resp = httpx.get(f"{GUMROAD_BASE}/sales", headers=_headers(), params=params, timeout=15.0)
    resp.raise_for_status()
    return resp.json().get("sales", [])


@with_retry()
def create_product(
    name: str,
    price_cents: int,
    description: str = "",
    url: str | None = None,
) -> dict:
    """
    Create a new Gumroad product.

    Args:
        name: Product name
        price_cents: Price in cents USD (e.g. 2700 = $27)
        description: Product description
        url: Custom URL slug (optional)

    Returns:
        Created product dict
    """
    data = {
        "name": name,
        "price": price_cents,
        "description": description,
    }
    if url:
        data["custom_permalink"] = url

    resp = httpx.post(f"{GUMROAD_BASE}/products", headers=_headers(), data=data, timeout=15.0)
    resp.raise_for_status()
    product = resp.json().get("product", {})
    logger.info(f"Gumroad product created: {name} (ID: {product.get('id')})")
    return product


@with_retry()
def get_revenue_summary() -> dict:
    """Return total revenue and product count summary."""
    products = list_products()
    sales = get_sales()
    total_revenue = sum(s.get("price", 0) for s in sales) / 100  # cents to dollars
    return {
        "product_count": len(products),
        "total_sales": len(sales),
        "total_revenue_usd": round(total_revenue, 2),
    }
