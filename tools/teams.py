"""
Microsoft Teams integration via Microsoft Graph API.

Setup:
  1. Azure Portal → App Registrations → New registration
  2. API Permissions → Add:
       - Chat.ReadWrite (delegated)
       - ChannelMessage.ReadWrite (delegated or application)
       - Team.ReadBasic.All (delegated)
  3. Certificates & Secrets → New client secret
  4. Set env vars below

Required env vars:
  MICROSOFT_TENANT_ID    — Azure Active Directory tenant ID
  MICROSOFT_CLIENT_ID    — App (client) ID
  MICROSOFT_CLIENT_SECRET — Client secret value

Note: Uses client-credentials flow (app-only). For user-delegated access
(DMs on behalf of a user), replace _get_token() with delegated OAuth flow.

Dependencies: httpx (already in requirements.txt)
"""
import logging
import os
import time

import httpx
from dotenv import load_dotenv

from tools.retry import check_http_response, with_retry

load_dotenv()

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Token cache — avoids one extra Azure roundtrip per API call
_token_cache: dict = {"token": None, "expires_at": 0.0}


def _get_token() -> str:
    """Acquire an access token via client credentials flow (cached for ~55 min)."""
    now = time.monotonic()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    tenant_id = os.getenv("MICROSOFT_TENANT_ID")
    client_id = os.getenv("MICROSOFT_CLIENT_ID")
    client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")

    if not all([tenant_id, client_id, client_secret]):
        raise ValueError(
            "MICROSOFT_TENANT_ID, MICROSOFT_CLIENT_ID, and MICROSOFT_CLIENT_SECRET must be set in .env"
        )

    resp = httpx.post(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=30,
    )
    check_http_response(resp, "Teams token")

    data = resp.json()
    _token_cache["token"] = data["access_token"]
    # Tokens are valid for 3600s; cache for 55 min to be safe
    _token_cache["expires_at"] = now + 3300
    return _token_cache["token"]


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/json"}


@with_retry()
def list_teams() -> list[dict]:
    """
    List all Teams the authenticated app can see.

    Returns:
        List of dicts: id, displayName
    """
    resp = httpx.get(
        f"{GRAPH_BASE}/groups?$filter=resourceProvisioningOptions/Any(x:x eq 'Team')",
        headers=_auth_headers(),
        timeout=30,
    )
    check_http_response(resp, "list_teams")

    teams = [{"id": t["id"], "displayName": t["displayName"]} for t in resp.json().get("value", [])]
    logger.info(f"Teams: found {len(teams)} teams")
    return teams


@with_retry()
def list_channels(team_id: str) -> list[dict]:
    """
    List channels in a Team.

    Args:
        team_id: Team ID from list_teams()

    Returns:
        List of dicts: id, displayName
    """
    resp = httpx.get(f"{GRAPH_BASE}/teams/{team_id}/channels", headers=_auth_headers(), timeout=30)
    check_http_response(resp, "list_channels")

    channels = [{"id": c["id"], "displayName": c["displayName"]} for c in resp.json().get("value", [])]
    logger.info(f"Teams: found {len(channels)} channels in team {team_id}")
    return channels


@with_retry()
def read_channel_messages(team_id: str, channel_id: str, limit: int = 10) -> list[dict]:
    """
    Read recent messages from a Teams channel.

    Args:
        team_id: Team ID
        channel_id: Channel ID from list_channels()
        limit: Max number of messages (default 10)

    Returns:
        List of dicts: id, sender, body, createdDateTime
    """
    resp = httpx.get(
        f"{GRAPH_BASE}/teams/{team_id}/channels/{channel_id}/messages",
        headers=_auth_headers(),
        params={"$top": limit},
        timeout=30,
    )
    check_http_response(resp, "read_channel_messages")

    messages = [
        {
            "id": msg["id"],
            "sender": msg.get("from", {}).get("user", {}).get("displayName", "Unknown"),
            "body": msg.get("body", {}).get("content", "")[:1000],
            "createdDateTime": msg.get("createdDateTime", ""),
        }
        for msg in resp.json().get("value", [])
    ]
    logger.info(f"Teams: read {len(messages)} messages from channel {channel_id}")
    return messages


@with_retry()
def post_to_channel(team_id: str, channel_id: str, message: str) -> dict:
    """
    Post a message to a Teams channel.

    Args:
        team_id: Team ID
        channel_id: Channel ID
        message: Plain text message

    Returns:
        Dict: id, createdDateTime
    """
    resp = httpx.post(
        f"{GRAPH_BASE}/teams/{team_id}/channels/{channel_id}/messages",
        headers=_auth_headers(),
        json={"body": {"contentType": "text", "content": message}},
        timeout=30,
    )
    check_http_response(resp, "post_to_channel", ok=(200, 201))

    data = resp.json()
    logger.info(f"Teams: posted message to channel {channel_id}")
    return {"id": data["id"], "createdDateTime": data.get("createdDateTime", "")}


@with_retry()
def send_dm(user_id: str, message: str) -> dict:
    """
    Send a direct message (1:1 chat) to a Teams user.

    Args:
        user_id: Azure AD user ID or UPN (email) of the recipient
        message: Plain text message

    Returns:
        Dict: chat_id, message_id
    """
    # Step 1: Create or retrieve a 1:1 chat
    chat_resp = httpx.post(
        f"{GRAPH_BASE}/chats",
        headers=_auth_headers(),
        json={
            "chatType": "oneOnOne",
            "members": [
                {
                    "@odata.type": "#microsoft.graph.aadUserConversationMember",
                    "roles": ["owner"],
                    "user@odata.bind": f"https://graph.microsoft.com/v1.0/users/{user_id}",
                }
            ],
        },
        timeout=30,
    )
    check_http_response(chat_resp, "send_dm (create chat)", ok=(200, 201))
    chat_id = chat_resp.json()["id"]

    # Step 2: Post the message
    msg_resp = httpx.post(
        f"{GRAPH_BASE}/chats/{chat_id}/messages",
        headers=_auth_headers(),
        json={"body": {"contentType": "text", "content": message}},
        timeout=30,
    )
    check_http_response(msg_resp, "send_dm (send message)", ok=(200, 201))

    data = msg_resp.json()
    logger.info(f"Teams: DM sent to user {user_id} in chat {chat_id}")
    return {"chat_id": chat_id, "message_id": data["id"]}
