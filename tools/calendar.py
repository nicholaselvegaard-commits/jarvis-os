"""
Google Calendar integration.

Setup required (one-time):
  1. Go to Google Cloud Console → create a project
  2. Enable the Google Calendar API
  3. Create OAuth 2.0 credentials (Desktop app) → download as
     config/google_credentials.json
  4. First run will open a browser to authorize — token saved to
     memory/google_token.json for future runs.

Dependencies: google-auth-oauthlib google-auth-httplib2 google-api-python-client
"""
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_FILE = Path("config/google_credentials.json")
TOKEN_FILE = Path("memory/google_token.json")

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build as _google_build
    _GOOGLE_AVAILABLE = True
except ImportError:
    _GOOGLE_AVAILABLE = False


def _get_service():
    """Authenticate and return the Google Calendar service object."""
    if not _GOOGLE_AVAILABLE:
        raise ImportError(
            "Install Google libs: "
            "pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client"
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
                    f"Google credentials not found at {CREDENTIALS_FILE}. "
                    "Download your OAuth2 credentials JSON from Google Cloud Console "
                    "and save it as config/google_credentials.json"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return _google_build("calendar", "v3", credentials=creds)


def list_events(days_ahead: int = 7, calendar_id: str = "primary") -> list[dict]:
    """
    List upcoming calendar events.

    Args:
        days_ahead: How many days ahead to look (default 7)
        calendar_id: Which calendar to query (default "primary")

    Returns:
        List of dicts: id, summary, start, end, location, description
    """
    service = _get_service()
    now = datetime.now(timezone.utc).isoformat()
    until = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).isoformat()

    result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=now,
            timeMax=until,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = [
        {
            "id": item.get("id"),
            "summary": item.get("summary", "(ingen tittel)"),
            "start": item["start"].get("dateTime", item["start"].get("date", "")),
            "end": item["end"].get("dateTime", item["end"].get("date", "")),
            "location": item.get("location", ""),
            "description": item.get("description", ""),
        }
        for item in result.get("items", [])
    ]

    logger.info(f"Fetched {len(events)} calendar events (next {days_ahead} days)")
    return events


def create_event(
    summary: str,
    start: str,
    end: str,
    description: str = "",
    location: str = "",
    calendar_id: str = "primary",
) -> dict:
    """
    Create a new calendar event.

    Args:
        summary: Event title
        start: ISO-8601 datetime, e.g. "2026-03-15T14:00:00+01:00"
        end: ISO-8601 datetime
        description: Optional description
        location: Optional location string
        calendar_id: Calendar to add the event to

    Returns:
        Dict with id, summary, htmlLink
    """
    service = _get_service()

    created = service.events().insert(
        calendarId=calendar_id,
        body={
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start, "timeZone": "Europe/Oslo"},
            "end": {"dateTime": end, "timeZone": "Europe/Oslo"},
        },
    ).execute()

    logger.info(f"Created calendar event: {summary} ({created['id']})")
    return {"id": created["id"], "summary": created.get("summary"), "htmlLink": created.get("htmlLink")}


def delete_event(event_id: str, calendar_id: str = "primary") -> str:
    """
    Delete a calendar event.

    Args:
        event_id: The event ID to delete
        calendar_id: Calendar containing the event

    Returns:
        Confirmation string
    """
    service = _get_service()
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    logger.info(f"Deleted calendar event: {event_id}")
    return f"Deleted event {event_id}."
