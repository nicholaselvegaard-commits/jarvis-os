"""Email sender via SMTP or SendGrid. Never sends without explicit trigger."""
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


def send_email(
    to: str | list[str],
    subject: str,
    body: str,
    html: bool = False,
    from_address: Optional[str] = None,
) -> bool:
    """
    Send an email via SMTP.

    Args:
        to: Recipient email(s).
        subject: Email subject.
        body: Email body (plain text or HTML).
        html: If True, send as HTML.
        from_address: Sender address (defaults to EMAIL_FROM env var).

    Returns:
        True if sent successfully.

    IMPORTANT: Never call this without explicit user trigger.
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    sender = from_address or os.getenv("EMAIL_FROM", smtp_user)

    if not smtp_user or not smtp_pass:
        raise ValueError("SMTP_USER and SMTP_PASSWORD must be set in environment")

    recipients = [to] if isinstance(to, str) else to

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    content_type = "html" if html else "plain"
    msg.attach(MIMEText(body, content_type))

    logger.info(f"Sending email to {recipients}: {subject!r}")
    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(sender, recipients, msg.as_string())
        logger.info("Email sent successfully")
        return True
    except Exception as e:
        logger.error(f"Email failed: {e}")
        raise
