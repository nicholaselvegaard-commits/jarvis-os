"""
SalesAgent — Autonomous cold outreach machine for Norwegian businesses.

Parses Groq plan → picks email template → sends via Outlook SMTP →
logs to CRM → saves to smart memory → notifies Nicholas on Telegram.

Usage:
    agent = SalesAgent()
    result = await agent.run("Find 5 potential clients for AI automation in Norway")
"""

import json
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from agents.jordan.tools.base_agent import BaseAgent
from tools.groq_client import chat as groq_chat

logger = logging.getLogger(__name__)

# ── SMTP config ────────────────────────────────────────────────────────────────
_SMTP_HOST = "smtp-mail.outlook.com"
_SMTP_PORT = 587
_EMAIL_USER = os.getenv("EMAIL_USER", "jordan.develepor@outlook.com")
_EMAIL_PASS = os.getenv("EMAIL_PASS", "")

# ── Groq system prompt ─────────────────────────────────────────────────────────
_SYSTEM = """\
Du er SalesAgent — autonom salgsmaskin for norske bedrifter.

Oppgave: Skriv en kald e-post til en norsk bedrift om AI-automatisering.

Svar ALLTID med et JSON-objekt og ingenting annet:
{
  "company": "Bedriftsnavn",
  "email": "kontakt@bedrift.no",
  "subject": "Kort og tydelig emnefelttekst",
  "body": "Kald e-post — maks 150 ord. Nevn ett konkret AI-brukstilfelle for DENNE bedriften. Avslutt med én klar CTA.",
  "crm_note": "Én setning om hvorfor dette er et lovende lead"
}

Regler:
- Skriv som en 17-åring fra Bodø som bygger et AI-imperium — direkte, spesifikk, ingen tomme fraser
- Start med problemet DERES, ikke hvem du er
- Norsk til norske bedrifter, engelsk til internasjonale
- Maks én metafor, null buzzword-soup
- Ingen "Jeg la merke til" eller "Jeg kom over" — fortell hva AI gjør FOR DEM
"""

# ── Email templates per nøkkelord ──────────────────────────────────────────────
_TEMPLATES: dict[str, str] = {
    "konsultasjon": """\
Hei,

Mange norske bedrifter bruker 10+ timer i uken på manuelt arbeid som AI kan overta på minutter.

Jeg tilbyr AI-konsultasjon der vi kartlegger nøyaktig hvor automatisering gir mest verdi for {company} — og setter det opp.

Gratis 30-minutters gjennomgang denne uken?

Med vennlig hilsen,
Nicholas Elvegaard
AI-automatisering | nicholas@nexus.no
""",
    "nettside": """\
Hei,

Nettstedet til {company} kan gjøre mye mer enn å vise informasjon — med AI kan det svare på kundehenvendelser, booke møter og kvalifisere leads automatisk, døgnet rundt.

Jeg bygger slike systemer for norske bedrifter. Ferdig på 1-2 uker.

Interessert i en rask demo?

Med vennlig hilsen,
Nicholas Elvegaard
AI-automatisering | nicholas@nexus.no
""",
    "automatisering": """\
Hei,

Jeg hjelper bedrifter som {company} med å automatisere repetitive arbeidsoppgaver med AI — rapporter, e-poster, databehandling og kundedialog.

Typisk resultat: 5-15 timer spart per ansatt per uke.

Kan jeg vise deg et konkret eksempel for deres bransje?

Med vennlig hilsen,
Nicholas Elvegaard
AI-automatisering | nicholas@nexus.no
""",
    "plc": """\
Hei,

PLC-systemer og industriell automatisering er ofte isolert fra moderne AI-verktøy. Jeg bygger broer mellom eksisterende PLC-infrastruktur og AI-lag som gir prediktivt vedlikehold, avviksdeteksjon og automatiske rapporter.

Ingen utskifting av eksisterende utstyr nødvendig.

Passer dette for {company}?

Med vennlig hilsen,
Nicholas Elvegaard
AI-automatisering | nicholas@nexus.no
""",
    "default": """\
Hei,

AI-automatisering er ikke lenger forbeholdt store selskaper — norske SMB-er kan nå sette opp systemer som håndterer kundeservice, lead-kvalifisering og intern rapportering automatisk.

Jeg bygger slike løsninger raskt og rimelig. {company} virker som en god kandidat.

Har du 20 minutter til en uforpliktende samtale?

Med vennlig hilsen,
Nicholas Elvegaard
AI-automatisering | nicholas@nexus.no
""",
}


def _pick_template(task: str, company: str) -> str:
    """Select the best email template based on task keywords."""
    task_lower = task.lower()
    for keyword in ("konsultasjon", "nettside", "automatisering", "plc"):
        if keyword in task_lower:
            return _TEMPLATES[keyword].format(company=company)
    return _TEMPLATES["default"].format(company=company)


def _send_smtp(to: str, subject: str, body: str) -> None:
    """Send email via Outlook SMTP with STARTTLS."""
    if not _EMAIL_PASS:
        raise EnvironmentError("EMAIL_PASS not set in environment")

    msg = MIMEMultipart("alternative")
    msg["From"] = _EMAIL_USER
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(_EMAIL_USER, _EMAIL_PASS)
        server.sendmail(_EMAIL_USER, to, msg.as_string())

    logger.info(f"SalesAgent: email sent → {to} | subject: {subject}")


def _parse_json(raw: str) -> dict[str, Any]:
    """Strip markdown fences and parse JSON from Groq response."""
    cleaned = raw.strip()
    for fence in ("```json", "```"):
        if cleaned.startswith(fence):
            cleaned = cleaned[len(fence):]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return json.loads(cleaned.strip())


class SalesAgent(BaseAgent):
    """
    Autonomous sales agent.

    Think (Groq) → pick template → send SMTP → CRM → memory → Telegram.
    """

    name = "sales"
    system_prompt = _SYSTEM
    max_tokens = 1024

    async def _act(self, task: str, plan: str) -> str:
        # ── 1. Parse Groq plan ────────────────────────────────────────────────
        try:
            data = _parse_json(plan)
        except Exception as exc:
            logger.warning(f"SalesAgent: JSON parse failed ({exc}), returning raw plan")
            return plan

        company: str = data.get("company", "")
        email_to: str = data.get("email", "")
        subject: str = data.get("subject", "")
        body: str = data.get("body", "")
        crm_note: str = data.get("crm_note", "")

        if not email_to or not body:
            return (
                f"SalesAgent: insufficient data to send. "
                f"company={company!r} email={email_to!r}. Raw plan: {plan[:200]}"
            )

        # If Groq body is short / missing context, enrich with template
        if len(body.split()) < 30:
            body = _pick_template(task, company)

        results: list[str] = []

        # ── 2. Send email via SMTP ────────────────────────────────────────────
        try:
            _send_smtp(to=email_to, subject=subject, body=body)
            results.append(f"Email sent to {company} ({email_to})")
        except Exception as exc:
            results.append(f"Email FAILED: {exc}")
            logger.error(f"SalesAgent SMTP error: {exc}", exc_info=True)

        # ── 3. Log to CRM ─────────────────────────────────────────────────────
        customer_id: str = ""
        try:
            from tools.crm import add_customer, update_stage
            customer_id = add_customer(
                name=company,
                email=email_to,
                stage="contacted",
                notes=crm_note or subject,
            )
            results.append(f"CRM: {company} added (id {customer_id})")
        except Exception as exc:
            logger.warning(f"SalesAgent CRM error: {exc}")
            results.append(f"CRM skipped: {exc}")

        # ── 4. Save to smart memory ───────────────────────────────────────────
        try:
            from memory.smart_memory import save
            save(
                category="lead",
                content=(
                    f"Cold email sent to {company} <{email_to}>. "
                    f"Subject: {subject}. Note: {crm_note}"
                ),
                priority=1,
            )
            results.append("Memory saved")
        except Exception as exc:
            logger.warning(f"SalesAgent memory save error: {exc}")

        # ── 5. Telegram notification ──────────────────────────────────────────
        try:
            from telegram_bot import notify_owner
            notify_owner(
                f"SalesAgent: e-post sendt\n"
                f"Bedrift: {company}\n"
                f"Til: {email_to}\n"
                f"Emne: {subject}\n"
                f"CRM-id: {customer_id or 'N/A'}"
            )
            results.append("Telegram notified")
        except Exception as exc:
            logger.warning(f"SalesAgent Telegram error: {exc}")

        summary = " | ".join(results)
        logger.info(f"SalesAgent done: {summary}")
        return summary
