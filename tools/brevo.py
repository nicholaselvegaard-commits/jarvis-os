"""
Brevo (Sendinblue) — email campaigns, transactional email, and contact lists.
Requires: BREVO_API_KEY
"""
import logging
import os

import httpx

from tools.retry import with_retry

logger = logging.getLogger(__name__)

BREVO_BASE = "https://api.brevo.com/v3"


def _headers() -> dict:
    key = os.getenv("BREVO_API_KEY", "")
    if not key:
        raise ValueError("BREVO_API_KEY not set in .env")
    return {"api-key": key, "Content-Type": "application/json"}


@with_retry()
def send_transactional(to_email: str, to_name: str, subject: str, html_content: str) -> str:
    """Send a transactional email via Brevo."""
    sender_name = os.getenv("BREVO_SENDER_NAME", "NicholasAgent")
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "nicholas@nicholasai.com")
    resp = httpx.post(
        f"{BREVO_BASE}/smtp/email",
        headers=_headers(),
        json={
            "sender": {"name": sender_name, "email": sender_email},
            "to": [{"email": to_email, "name": to_name}],
            "subject": subject,
            "htmlContent": html_content,
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    msg_id = resp.json().get("messageId", "")
    logger.info(f"Brevo: sent to {to_email} — ID {msg_id}")
    return msg_id


@with_retry()
def add_contact(email: str, first_name: str = "", last_name: str = "", list_ids: list[int] | None = None) -> dict:
    """Add or update a contact in Brevo."""
    resp = httpx.post(
        f"{BREVO_BASE}/contacts",
        headers=_headers(),
        json={
            "email": email,
            "attributes": {"FIRSTNAME": first_name, "LASTNAME": last_name},
            "listIds": list_ids or [],
            "updateEnabled": True,
        },
        timeout=10.0,
    )
    if resp.status_code in (201, 204):
        logger.info(f"Brevo: contact added/updated {email}")
        return {"email": email, "status": "ok"}
    resp.raise_for_status()
    return resp.json()


@with_retry()
def get_account() -> dict:
    """Return Brevo account info and plan details."""
    resp = httpx.get(f"{BREVO_BASE}/account", headers=_headers(), timeout=10.0)
    resp.raise_for_status()
    return resp.json()
