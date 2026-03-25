"""
MCP Board — kommunikasjonskanal mellom NEXUS og Jordan/Manus.

Eksakte endepunkter (fra mcp_board_format.txt):
  POST /board                  — Send melding
  GET  /board                  — Les alle meldinger
  GET  /board/unread/nexus     — Hent uleste meldinger til NEXUS
  GET  /health                 — Sjekk om boardet er oppe

Meldingstyper: "task" | "signal" | "insight" | "message"
NEXUS sin source: "nexus"
"""

import os
import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MCP_URL = os.getenv("MCP_BOARD_URL", "http://89.167.100.7:8001")
MCP_SECRET = os.getenv("MCP_SECRET", "jordan-manus-secret-2026")
HEADERS = {
    "x-mcp-secret": MCP_SECRET,
    "Content-Type": "application/json",
}


class MCPBoard:
    def post(self, type: str, title: str, content: str, metadata: dict = {}) -> dict:
        """
        Post en melding til boardet.

        Args:
            type:     "task" | "signal" | "insight" | "message"
            title:    Kort tittel på meldingen
            content:  Innholdet (tekst)
            metadata: Valgfri ekstra data som dict
        """
        payload = {
            "type": type,
            "source": "nexus",
            "title": title,
            "content": content,
            "metadata": metadata,
        }
        try:
            r = requests.post(f"{MCP_URL}/board", json=payload, headers=HEADERS, timeout=10)
            r.raise_for_status()
            logger.info(f"MCP POST [{type}] '{title[:60]}'")
            return r.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"MCP POST feil: {e}")
            return {"error": str(e)}

    def read(self, limit: int = 20) -> list:
        """Les alle meldinger på boardet."""
        try:
            r = requests.get(
                f"{MCP_URL}/board",
                params={"limit": limit},
                headers=HEADERS,
                timeout=10,
            )
            r.raise_for_status()
            return r.json().get("entries", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"MCP GET feil: {e}")
            return []

    def get_unread(self) -> list:
        """Hent uleste meldinger til NEXUS."""
        try:
            r = requests.get(
                f"{MCP_URL}/board/unread/nexus",
                headers=HEADERS,
                timeout=10,
            )
            r.raise_for_status()
            messages = r.json()
            if messages:
                logger.info(f"MCP inbox: {len(messages)} uleste meldinger")
            return messages if isinstance(messages, list) else []
        except requests.exceptions.RequestException as e:
            logger.error(f"MCP unread feil: {e}")
            return []

    def health(self) -> bool:
        """Sjekk om MCP-boardet er tilgjengelig."""
        try:
            r = requests.get(f"{MCP_URL}/health", headers=HEADERS, timeout=5)
            return r.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def delegate_to_jordan(self, task_title: str, task_description: str) -> dict:
        """Deleger en oppgave til Jordan."""
        return self.post(
            type="task",
            title=f"[NEXUS→JORDAN] {task_title}",
            content=task_description,
        )

    def post_daily_report(self, report_text: str) -> dict:
        """Send daglig rapport til boardet."""
        return self.post(
            type="insight",
            title="NEXUS Daglig Rapport",
            content=report_text,
        )

    def post_signal(self, title: str, content: str) -> dict:
        """Send et viktig signal til boardet (f.eks. ny kontrakt, feil)."""
        return self.post(type="signal", title=title, content=content)


# Singleton-instans — importér denne i stedet for å lage nye objekter
board = MCPBoard()
