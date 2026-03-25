"""
NEXUS Email Reader — leser innboksen for lead-svar.

Kobler til via IMAP og henter e-poster fra kjente leads.
Trigger: kalles av monitor_agent og /replies kommando.

Env vars:
    IMAP_HOST     imap.gmail.com (default)
    EMAIL_ADDRESS avsender-adressen NEXUS bruker
    EMAIL_PASSWORD Gmail app-passord (ikke vanlig passord)
"""

import imaplib
import email
import os
import logging
from datetime import datetime, timedelta
from email.header import decode_header
from typing import List, Dict

logger = logging.getLogger(__name__)

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")


def _decode_str(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    parts = decode_header(raw)
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="ignore"))
        else:
            result.append(part)
    return " ".join(result)


def _get_body(msg) -> str:
    """Ekstraher tekstinnhold fra e-postmelding."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                try:
                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    break
                except Exception:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        except Exception:
            pass
    return body.strip()[:2000]


def get_recent_replies(days: int = 3) -> List[Dict]:
    """
    Hent e-poster mottatt siste N dager.

    Returns:
        Liste med dicts: {from, subject, date, snippet, is_reply}
    """
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        return [{"error": "IMAP ikke konfigurert — sett EMAIL_ADDRESS og EMAIL_PASSWORD"}]

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("INBOX")

        since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(SINCE "{since}")')

        ids = data[0].split()
        results = []

        for uid in ids[-30:]:  # Maks 30 nyeste
            try:
                _, msg_data = mail.fetch(uid, "(RFC822)")
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                sender = _decode_str(msg.get("From", ""))
                subject = _decode_str(msg.get("Subject", ""))
                date_str = msg.get("Date", "")
                body = _get_body(msg)
                is_reply = subject.lower().startswith(("re:", "sv:", "aw:"))

                results.append({
                    "from": sender,
                    "subject": subject,
                    "date": date_str,
                    "snippet": body[:300],
                    "is_reply": is_reply,
                })
            except Exception as e:
                logger.warning(f"Kunne ikke lese e-post {uid}: {e}")

        mail.logout()
        return results

    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP-feil: {e}")
        return [{"error": f"IMAP-tilkobling feilet: {e}"}]
    except Exception as e:
        logger.error(f"email_reader feil: {e}")
        return [{"error": str(e)}]


def count_replies(days: int = 3) -> Dict:
    """Rask telling — antall svar og nye meldinger."""
    mails = get_recent_replies(days)
    if mails and "error" in mails[0]:
        return {"configured": False, "error": mails[0]["error"]}
    replies = [m for m in mails if m.get("is_reply")]
    return {
        "configured": True,
        "total_received": len(mails),
        "replies": len(replies),
        "days": days,
        "latest": replies[0] if replies else None,
    }


def format_replies_for_nexus(days: int = 3) -> str:
    """Formatert oversikt klar for Telegram / LLM-injeksjon."""
    data = count_replies(days)
    if not data.get("configured"):
        return f"E-post ikke konfigurert: {data.get('error', 'ukjent feil')}"

    mails = get_recent_replies(days)
    replies = [m for m in mails if m.get("is_reply")]

    if not replies:
        return f"Ingen svar siste {days} dager ({data['total_received']} mottatt totalt)."

    lines = [f"{len(replies)} svar siste {days} dager:\n"]
    for r in replies[:10]:
        lines.append(f"• Fra: {r['from']}\n  Emne: {r['subject']}\n  {r['snippet'][:100]}\n")

    return "\n".join(lines)
