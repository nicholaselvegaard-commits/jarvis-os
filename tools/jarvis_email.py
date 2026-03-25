"""
Jarvis's own email client — sends from jordan.develepor@outlook.com autonomously.
Uses Resend API (free 100/day) — no OAuth2 headaches.

Usage:
    from tools.jarvis_email import send_email
"""
import logging
import os
import httpx

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
JORDAN_EMAIL = os.getenv("JORDAN_SMTP_USER", "jordan.develepor@outlook.com")
# Resend free tier sender — reply-to is Jarvis's real address
RESEND_FROM = "Jarvis <onboarding@resend.dev>"
BASE_URL = "https://api.resend.com/emails"


def send_email(to: str, subject: str, body: str) -> dict:
    """
    Send email as Jarvis. No approval needed — Jarvis's own identity.
    Sends via Resend (free 100/day). Reply-to is jordan.develepor@outlook.com.
    """
    if not RESEND_API_KEY:
        raise ValueError("RESEND_API_KEY not set in .env — get one free at resend.com")

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "from": RESEND_FROM,
        "reply_to": JORDAN_EMAIL,
        "to": [to],
        "subject": subject,
        "text": body,
    }

    with httpx.Client(timeout=15) as client:
        r = client.post(BASE_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()

    logger.info(f"Jarvis email sent via Resend → {to} | {subject}")
    return {"status": "sent", "to": to, "subject": subject, "id": data.get("id")}


def send_email_with_html(to: str, subject: str, body_text: str, body_html: str) -> dict:
    """Send email with HTML content."""
    if not RESEND_API_KEY:
        raise ValueError("RESEND_API_KEY not set in .env")

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "from": RESEND_FROM,
        "reply_to": JORDAN_EMAIL,
        "to": [to],
        "subject": subject,
        "text": body_text,
        "html": body_html,
    }

    with httpx.Client(timeout=15) as client:
        r = client.post(BASE_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()

    logger.info(f"Jarvis HTML email sent via Resend → {to} | {subject}")
    return {"status": "sent", "to": to, "subject": subject, "id": data.get("id")}
