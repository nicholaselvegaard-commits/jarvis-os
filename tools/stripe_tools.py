"""
Stripe-verktøy — Jarvis kan opprette produkter, checkout-lenker og sjekke inntekter.

Krever STRIPE_SECRET_KEY i .env (live key).
"""
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BASE = "https://api.stripe.com/v1"


def _headers() -> dict:
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        raise ValueError("STRIPE_SECRET_KEY not set")
    return {"Authorization": f"Bearer {key}"}


def create_payment_link(
    name: str,
    amount_nok: int,
    description: str = "",
    quantity: int = 1,
) -> dict:
    """
    Opprett et Stripe-produkt og en checkout-lenke på sekunder.

    Args:
        name:        Produktnavn, f.eks. "AI-nettside pakke"
        amount_nok:  Pris i NOK (øre = amount_nok * 100)
        description: Produktbeskrivelse
        quantity:    Antall (1 for engangs)

    Returns:
        {url, product_id, price_id, link_id}
    """
    h = _headers()

    # 1. Opprett produkt
    prod_resp = httpx.post(f"{BASE}/products", headers=h,
                            data={"name": name, "description": description}, timeout=15)
    prod_resp.raise_for_status()
    product_id = prod_resp.json()["id"]

    # 2. Opprett pris
    price_resp = httpx.post(f"{BASE}/prices", headers=h, data={
        "product": product_id,
        "unit_amount": amount_nok * 100,  # øre
        "currency": "nok",
    }, timeout=15)
    price_resp.raise_for_status()
    price_id = price_resp.json()["id"]

    # 3. Opprett payment link
    link_resp = httpx.post(f"{BASE}/payment_links", headers=h, data={
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": str(quantity),
    }, timeout=15)
    link_resp.raise_for_status()
    link = link_resp.json()

    logger.info(f"Stripe link created: {name} — {amount_nok} NOK — {link['url']}")
    return {
        "url": link["url"],
        "product_id": product_id,
        "price_id": price_id,
        "link_id": link["id"],
        "amount_nok": amount_nok,
        "name": name,
    }


def get_recent_payments(limit: int = 10) -> list[dict]:
    """
    Hent siste betalinger fra Stripe.

    Returns:
        Liste med {amount_nok, currency, status, description, created}
    """
    h = _headers()
    resp = httpx.get(f"{BASE}/payment_intents", headers=h,
                      params={"limit": limit}, timeout=15)
    resp.raise_for_status()
    items = resp.json().get("data", [])
    return [
        {
            "amount_nok": item["amount"] / 100,
            "currency": item["currency"],
            "status": item["status"],
            "description": item.get("description", ""),
            "created": item["created"],
        }
        for item in items
    ]


def get_total_revenue_stripe() -> float:
    """Hent total inntekt fra Stripe i NOK."""
    payments = get_recent_payments(limit=100)
    return sum(p["amount_nok"] for p in payments if p["status"] == "succeeded")


def create_invoice(
    customer_email: str,
    items: list[dict],
    due_days: int = 14,
) -> dict:
    """
    Opprett og send en faktura til en kunde.

    Args:
        customer_email: Kundens e-post
        items: [{"description": str, "amount_nok": int}]
        due_days: Betalingsfrist i dager

    Returns:
        {invoice_id, hosted_url, amount_due}
    """
    h = _headers()

    # Finn eller opprett kunde
    cust_resp = httpx.get(f"{BASE}/customers", headers=h,
                           params={"email": customer_email, "limit": 1}, timeout=15)
    cust_resp.raise_for_status()
    customers = cust_resp.json().get("data", [])
    if customers:
        customer_id = customers[0]["id"]
    else:
        new_cust = httpx.post(f"{BASE}/customers", headers=h,
                               data={"email": customer_email}, timeout=15)
        new_cust.raise_for_status()
        customer_id = new_cust.json()["id"]

    # Opprett faktura
    inv_resp = httpx.post(f"{BASE}/invoices", headers=h, data={
        "customer": customer_id,
        "collection_method": "send_invoice",
        "days_until_due": str(due_days),
    }, timeout=15)
    inv_resp.raise_for_status()
    invoice_id = inv_resp.json()["id"]

    # Legg til linjer
    for item in items:
        httpx.post(f"{BASE}/invoiceitems", headers=h, data={
            "customer": customer_id,
            "invoice": invoice_id,
            "description": item["description"],
            "amount": item["amount_nok"] * 100,
            "currency": "nok",
        }, timeout=15).raise_for_status()

    # Send
    send_resp = httpx.post(f"{BASE}/invoices/{invoice_id}/send", headers=h, timeout=15)
    send_resp.raise_for_status()
    inv = send_resp.json()

    logger.info(f"Invoice sent to {customer_email}: {invoice_id}")
    return {
        "invoice_id": invoice_id,
        "hosted_url": inv.get("hosted_invoice_url", ""),
        "amount_due": inv["amount_due"] / 100,
        "customer_email": customer_email,
    }
