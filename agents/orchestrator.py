"""
NEXUS Orchestrator — Master Agent node.
"""

import os
import logging
from pathlib import Path
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from core.state import NexusState

logger = logging.getLogger(__name__)

_SEARCH_PATHS = [
    Path(__file__).parent.parent / "master_agent_system_prompt.txt",
    Path("/opt/nexus/master_agent_system_prompt.txt"),
    Path(__file__).parent.parent.parent / "MAESTRO AGENT" / "master_agent_system_prompt.txt",
]

_FALLBACK_PROMPT = """Du er NEXUS — en autonom AI-agent som genererer inntekt for din eier fra Bodø, Norge.
Du er ikke en chatbot. Du er strategisk, handlingsorientert og proaktiv.
Analyser situasjonen og bestem neste steg: research, sales, mcp, reporter, eller __end__."""

VALID_DECISIONS = {"research", "sales", "mcp", "reporter", "__end__"}

ROUTING_INSTRUCTIONS = """
Bestem neste steg og svar KUN med ett av disse ordene (ingenting annet):
- research   → Hent leads fra Apollo.io
- sales      → Send e-poster til leads i køen
- mcp        → Les/svar på MCP-board meldinger
- reporter   → Generer og send daglig rapport
- __end__    → Ingen flere oppgaver nå
"""


def _load_system_prompt() -> str:
    for path in _SEARCH_PATHS:
        if path.exists():
            logger.info(f"System-prompt lastet fra: {path}")
            return path.read_text(encoding="utf-8")
    logger.warning("master_agent_system_prompt.txt ikke funnet — bruker fallback")
    return _FALLBACK_PROMPT


SYSTEM_PROMPT = _load_system_prompt()

llm = ChatAnthropic(
    model="claude-sonnet-4-6",
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    max_tokens=512,
)


def orchestrator_node(state: NexusState) -> NexusState:
    task = state.get("task", "Kjør morgenrutine")
    leads = state.get("leads", [])
    emails_today = state.get("emails_today", 0)
    mcp_inbox = state.get("mcp_inbox", [])
    errors = state.get("errors", [])

    status_summary = (
        f"OPPGAVE: {task}\n"
        f"Leads i kø: {len(leads)} | "
        f"E-poster i dag: {emails_today} | "
        f"Uleste MCP: {len(mcp_inbox)} | "
        f"Feil: {len(errors)}\n\n"
        f"{ROUTING_INSTRUCTIONS}"
    )

    try:
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=status_summary),
        ])
        # Rens svaret — ta kun første ord, lowercase
        decision = response.content.strip().lower().split()[0].rstrip(".")
        logger.info(f"Orchestrator: {decision}")
    except Exception as e:
        logger.error(f"Orchestrator LLM feil: {e}")
        decision = "__end__"

    if decision not in VALID_DECISIONS:
        logger.warning(f"Ugyldig routing '{decision}' — avslutter")
        decision = "__end__"

    return {**state, "next": decision}
