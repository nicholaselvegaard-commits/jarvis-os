"""
E-post verktøy for NEXUS.

Bruker Instantly.ai for storskala outreach (primær).
Fallback til Outlook SMTP for enkeltmeldinger og eier-varsler.
"""

import os
import smtplib
import requests
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

logger = logging.getLogger(__name__)

# Instantly.ai
INSTANTLY_API_KEY = os.getenv("INSTANTLY_API_KEY", "")
INSTANTLY_BASE = "https://api.instantly.ai/api/v1"

# Outlook SMTP (fallback + eier-varsler)
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASS = os.getenv("EMAIL_PASS", "")
EMAIL_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "smtp-mail.outlook.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))


# ---------------------------------------------------------------------------
# E-postmaler
# ---------------------------------------------------------------------------

COLD_EMAIL_TEMPLATE_NO = """\
Hei {first_name},

{observation}

Vi hjelper bedrifter som {company} med å automatisere {pain_point} med AI \
— typisk sparer våre kunder 10-15 timer per uke og reduserer kostnader med 30-40%.

Konkret: Vi bygde en AI-løsning for en tilsvarende bedrift som kuttet \
[prosess] fra 8 timer til 20 minutter per uke.

Har du 15 minutter denne uken til en rask demo?

Mvh,
NEXUS | Elvegaard Labs, Bodø
"""

# Mal B: Ingen generisk "bare sjekker inn" — tilfør alltid ny verdi
FOLLOWUP_EMAIL_TEMPLATE_NO = """\
Hei {first_name},

En rask tanke jeg ville dele med deg:

{new_value}

Dette er direkte relevant for {company}. Om du fortsatt er åpen for en \
15-minutters samtale, er jeg tilgjengelig denne uken.

Mvh,
NEXUS | Elvegaard Labs, Bodø
"""

# Mal C: Etter møte/demo
POST_DEMO_EMAIL_TEMPLATE_NO = """\
Hei {first_name},

Takk for samtalen {meeting_date}. Som lovet, her er et sammendrag:

1. Utfordring: {pain_point}
2. Løsning: {proposed_solution}
3. Investering: {price_options}
4. Tidsramme: {timeline}
5. Neste steg: {next_step}

Tilbudet gjelder til {offer_expiry}. Start allerede {start_date} om det passer.

Mvh,
NEXUS | Elvegaard Labs, Bodø
"""


# ---------------------------------------------------------------------------
# Instantly.ai — storskala outreach
# ---------------------------------------------------------------------------

def instantly_add_lead(
    email: str,
    first_name: str,
    last_name: str,
    company: str,
    campaign_id: str,
) -> bool:
    """Legg til et lead i en Instantly.ai-kampanje."""
    if not INSTANTLY_API_KEY:
        logger.warning("INSTANTLY_API_KEY mangler — bruker SMTP fallback")
        return False

    payload = {
        "api_key": INSTANTLY_API_KEY,
        "campaign_id": campaign_id,
        "skip_if_in_workspace": True,
        "leads": [
            {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "company_name": company,
            }
        ],
    }

    try:
        resp = requests.post(
            f"{INSTANTLY_BASE}/lead/add",
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        logger.info(f"Instantly: Lead {email} lagt til i kampanje {campaign_id}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Instantly lead-feil: {e}")
        return False


def instantly_get_campaigns() -> list:
    """Hent alle aktive kampanjer fra Instantly.ai."""
    if not INSTANTLY_API_KEY:
        return []
    try:
        resp = requests.get(
            f"{INSTANTLY_BASE}/campaign/list",
            params={"api_key": INSTANTLY_API_KEY, "limit": 20},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])
    except requests.exceptions.RequestException as e:
        logger.error(f"Instantly kampanjer feil: {e}")
        return []


# ---------------------------------------------------------------------------
# SMTP — enkeltmeldinger og eier-varsler
# ---------------------------------------------------------------------------

def _smtp_send(to: str, subject: str, body: str, from_name: str = "NEXUS") -> bool:
    if not EMAIL_USER or not EMAIL_PASS:
        logger.error("SMTP-konfigurasjon mangler")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{EMAIL_USER}>"
    msg["To"] = to
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        logger.info(f"SMTP: E-post sendt til {to}")
        return True
    except smtplib.SMTPException as e:
        logger.error(f"SMTP feil til {to}: {e}")
        return False


# ---------------------------------------------------------------------------
# Offentlig API — brukes av agents
# ---------------------------------------------------------------------------

def send_cold_email(lead: dict, campaign_id: Optional[str] = None) -> bool:
    """
    Send kald e-post til et lead.
    Bruker Instantly.ai hvis campaign_id er satt, ellers SMTP.
    """
    email = lead.get("email", "")
    if not email:
        return False

    if INSTANTLY_API_KEY and campaign_id:
        return instantly_add_lead(
            email=email,
            first_name=lead.get("first_name", ""),
            last_name=lead.get("last_name", ""),
            company=lead.get("company", ""),
            campaign_id=campaign_id,
        )

    # SMTP fallback
    body = COLD_EMAIL_TEMPLATE_NO.format(
        first_name=lead.get("first_name", "der"),
        company=lead.get("company", "dere"),
    )
    return _smtp_send(
        to=email,
        subject=f"AI-automatisering for {lead.get('company', 'dere')} — 15 min demo?",
        body=body,
    )


def send_followup_email(lead: dict, days_since: int = 3) -> bool:
    """Send oppfølgings-e-post via SMTP."""
    email = lead.get("email", "")
    if not email:
        return False

    body = FOLLOWUP_EMAIL_TEMPLATE_NO.format(
        first_name=lead.get("first_name", "der"),
        company=lead.get("company", "dere"),
        days_since=days_since,
    )
    return _smtp_send(
        to=email,
        subject=f"Re: AI-automatisering for {lead.get('company', 'dere')}",
        body=body,
    )


def notify_owner(subject: str, body: str) -> bool:
    """Send varsling til eier via SMTP."""
    owner = os.getenv("OWNER_EMAIL", "")
    if not owner:
        return False
    return _smtp_send(to=owner, subject=subject, body=body)
