"""
MCP Agent — Leser og svarer på meldinger fra Jordan/Manus via MCP-board.
"""

import os
import logging
from datetime import datetime
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from core.state import NexusState
from tools.mcp_board import board

logger = logging.getLogger(__name__)

llm = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    max_tokens=512,
)

MCP_SYSTEM = """Du er NEXUS. Du leser meldinger fra Jordan og Manus på MCP-boardet og svarer kort og konkret.
Svar på norsk med mindre meldingen er på et annet språk.
Vær handlingsorientert — si hva du har gjort eller vil gjøre. Maks 3 setninger."""


def mcp_node(state: NexusState) -> NexusState:
    """Les uleste MCP-meldinger og generer svar til Jordan/Manus."""
    logger.info("MCP Agent: Sjekker MCP-board")

    inbox = board.get_unread()
    responses_sent = []
    errors = state.get("errors", [])

    for msg in inbox:
        # MCP-board bruker 'source', ikke 'from'
        sender = msg.get("source", msg.get("from", "ukjent"))
        content = msg.get("content", "")
        msg_type = msg.get("type", "info")

        if not content:
            continue

        logger.info(f"MCP Agent: [{sender}] {content[:80]}")

        try:
            response = llm.invoke([
                SystemMessage(content=MCP_SYSTEM),
                HumanMessage(content=f"Melding fra {sender} [{msg_type}]:\n{content}\n\nSvar kortfattet."),
            ])
            reply = response.content.strip()

            board.post(
                type="message",
                title=f"[NEXUS→{sender.upper()}] Svar",
                content=reply,
            )
            responses_sent.append({"to": sender, "reply": reply[:100]})
            logger.info(f"MCP Agent: Svarte til {sender}")

        except Exception as e:
            err = f"{datetime.utcnow().isoformat()} — MCP feil mot {sender}: {e}"
            logger.error(err)
            errors.append(err)

    return {
        **state,
        "mcp_inbox": inbox,
        "mcp_sent": state.get("mcp_sent", []) + responses_sent,
        "next": "reporter",
        "errors": errors,
    }
