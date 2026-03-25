"""
Gmail integration via Google Gmail API (OAuth2).

Setup (one-time):
  1. Google Cloud Console → create/select project
  2. Enable Gmail API
  3. Create OAuth 2.0 credentials (Desktop app) → download as
     config/google_credentials.json
  4. First run opens a browser for authorization — token saved to
     memory/gmail_token.json for all future runs.

Dependencies: google-auth-oauthlib google-auth-httplib2 google-api-python-client
"""
import base64
import logging
from dataclasses import dataclass
from email.mime.text import MIMEText
from pathlib import Path

from tools.retry import with_retry

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CREDENTIALS_FILE = Path("config/google_credentials.json")
TOKEN_FILE = Path("memory/gmail_token.json")

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build as _google_build
    _GOOGLE_AVAILABLE = True
except ImportError:
    _GOOGLE_AVAILABLE = False


@dataclass
class GmailMessage:
    id: str
    thread_id: str
    sender: str
    subject: str
    date: str
    body: str
    is_unread: bool


def _get_service():
    """Authenticate and return the Gmail API service."""
    if not _GOOGLE_AVAILABLE:
        raise ImportError(
            "Install: pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client"
        )

    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"Missing {CREDENTIALS_FILE}. Download OAuth2 credentials JSON from "
                    "Google Cloud Console and save it there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return _google_build("gmail", "v1", credentials=creds)


def _decode_body(payload: dict) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        text = _decode_body(part)
        if text:
            return text

    return ""


def _get_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _parse_message(msg: dict) -> GmailMessage:
    headers = msg.get("payload", {}).get("headers", [])
    body = _decode_body(msg.get("payload", {}))
    return GmailMessage(
        id=msg["id"],
        thread_id=msg["threadId"],
        sender=_get_header(headers, "From"),
        subject=_get_header(headers, "Subject"),
        date=_get_header(headers, "Date"),
        body=body[:4000],
        is_unread="UNREAD" in msg.get("labelIds", []),
    )


@with_retry()
def read_unread(limit: int = 10) -> list[GmailMessage]:
    """
    Fetch unread emails from Gmail inbox.

    Args:
        limit: Max number of messages to return (default 10)

    Returns:
        List of GmailMessage dataclasses
    """
    service = _get_service()
    result = service.users().messages().list(
        userId="me",
        labelIds=["UNREAD", "INBOX"],
        maxResults=limit,
    ).execute()

    messages = []
    for item in result.get("messages", []):
        msg = service.users().messages().get(userId="me", id=item["id"], format="full").execute()
        messages.append(_parse_message(msg))

    logger.info(f"Fetched {len(messages)} unread Gmail messages")
    return messages


@with_retry()
def search_inbox(query: str, limit: int = 10) -> list[GmailMessage]:
    """
    Search Gmail using Gmail query syntax.

    Args:
        query: e.g. 'from:atle@skole.no subject:prosjekt is:unread'
        limit: Max number of messages (default 10)

    Returns:
        List of GmailMessage dataclasses
    """
    service = _get_service()
    result = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=limit,
    ).execute()

    messages = []
    for item in result.get("messages", []):
        msg = service.users().messages().get(userId="me", id=item["id"], format="full").execute()
        messages.append(_parse_message(msg))

    logger.info(f"Gmail search '{query}': {len(messages)} results")
    return messages


@with_retry()
def send_email(to: str, subject: str, body: str) -> str:
    """
    Send a new email via Gmail.

    Args:
        to: Recipient address
        subject: Subject line
        body: Plain text body

    Returns:
        Sent message ID
    """
    service = _get_service()

    mime_msg = MIMEText(body)
    mime_msg["to"] = to
    mime_msg["subject"] = subject

    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()

    logger.info(f"Gmail: sent to {to} — ID {sent['id']}")
    return sent["id"]


@with_retry()
def reply_to_email(
    message_id: str,
    thread_id: str,
    to: str,
    subject: str,
    body: str,
) -> str:
    """
    Reply to an existing Gmail thread.

    Args:
        message_id: ID of the message being replied to
        thread_id: Thread ID (from GmailMessage.thread_id)
        to: Recipient address
        subject: Subject (usually "Re: <original subject>")
        body: Plain text reply

    Returns:
        Sent message ID
    """
    service = _get_service()

    mime_msg = MIMEText(body)
    mime_msg["to"] = to
    mime_msg["subject"] = subject
    mime_msg["In-Reply-To"] = message_id
    mime_msg["References"] = message_id

    raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
    sent = service.users().messages().send(
        userId="me",
        body={"raw": raw, "threadId": thread_id},
    ).execute()

    logger.info(f"Gmail: reply sent to {to} in thread {thread_id}")
    return sent["id"]


@with_retry()
def mark_as_read(message_id: str) -> None:
    """Remove the UNREAD label from a Gmail message."""
    service = _get_service()
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()
    logger.info(f"Gmail: marked {message_id} as read")
