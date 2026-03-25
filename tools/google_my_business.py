"""
Google Business Profile (My Business) management.
Requires: google_credentials.json (same OAuth file as calendar/gmail)
SCOPE: https://www.googleapis.com/auth/business.manage
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/business.manage"]
CREDENTIALS_FILE = Path("config/google_credentials.json")
TOKEN_FILE = Path("memory/gmb_token.json")

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build as _google_build
    _GOOGLE_AVAILABLE = True
except ImportError:
    _GOOGLE_AVAILABLE = False


def _get_service():
    if not _GOOGLE_AVAILABLE:
        raise ImportError("Install: pip install google-auth-oauthlib google-api-python-client")

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(f"Missing {CREDENTIALS_FILE}")
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return _google_build("mybusiness", "v4", credentials=creds, discoveryServiceUrl=(
        "https://developers.google.com/my-business/api/discovery"
    ))


def list_locations(account_id: str) -> list[dict]:
    """List all business locations for an account."""
    service = _get_service()
    result = service.accounts().locations().list(parent=f"accounts/{account_id}").execute()
    return result.get("locations", [])


def get_reviews(account_id: str, location_id: str, limit: int = 10) -> list[dict]:
    """Get recent Google reviews for a location."""
    service = _get_service()
    result = service.accounts().locations().reviews().list(
        parent=f"accounts/{account_id}/locations/{location_id}",
        pageSize=limit,
    ).execute()
    return result.get("reviews", [])


def reply_to_review(account_id: str, location_id: str, review_id: str, reply: str) -> dict:
    """Reply to a Google review."""
    service = _get_service()
    result = service.accounts().locations().reviews().updateReply(
        name=f"accounts/{account_id}/locations/{location_id}/reviews/{review_id}/reply",
        body={"comment": reply},
    ).execute()
    logger.info(f"GMB: replied to review {review_id}")
    return result


def update_business_info(account_id: str, location_id: str, updates: dict) -> dict:
    """Update business info (description, hours, phone, website)."""
    service = _get_service()
    result = service.accounts().locations().patch(
        name=f"accounts/{account_id}/locations/{location_id}",
        updateMask=",".join(updates.keys()),
        body=updates,
    ).execute()
    logger.info(f"GMB: updated {location_id}")
    return result
