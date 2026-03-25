"""
Delegate tool — Jarvis uses this to hand off tasks to sub-agents.

Usage by Jarvis (via Claude tool-use):
    delegate(agent="sales", task="Send a pitch to Bodø Energi about AI billing optimization")
    delegate(agent="research", task="What's the current state of AI in Norwegian SMEs?")
    delegate(agent="finance", task="Should I buy ETH right now?")

Returns the sub-agent's result as a string.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

# Human-readable descriptions for Jarvis's awareness
AGENT_DESCRIPTIONS = {
    "sales":     "Finds leads + sends cold emails autonomously from Jarvis's email",
    "research":  "Deep web research → structured Markdown reports",
    "finance":   "Live market data → BUY/SELL signals (stocks + crypto)",
    "content":   "Writes Twitter/LinkedIn/Reddit posts for Nicholas's brand",
    "dev":       "Builds and deploys full-stack apps for clients",
    "scout":     "Scans internet 24/7 for new APIs and opportunities",
    "crypto":    "On-chain analytics, DeFi yields, Phantom wallet monitoring",
    "email":     "Reads Jarvis's inbox, classifies and responds to emails",
    "bodo":      "Norwegian/Bodø market specialist — local leads + pricing",
    "growth":    "Product launches, Gumroad, passive income streams",
    "architect": "Designs complete prompt templates + specs for new AI agents",
}


async def delegate(agent: str, task: str) -> str:
    """
    Hand off a task to a specialized sub-agent.

    Args:
        agent: Agent name — one of: sales, research, finance, content,
               dev, scout, crypto, email, bodo, growth
        task: Natural language task description

    Returns:
        Result string from the sub-agent
    """
    from agents import REGISTRY

    agent = agent.lower().strip()
    if agent not in REGISTRY:
        available = ", ".join(REGISTRY.keys())
        return f"Unknown agent '{agent}'. Available: {available}"

    logger.info(f"delegate: Jarvis → {agent}: {task[:80]}")

    try:
        agent_instance = REGISTRY[agent]()
        result = await agent_instance.run(task)
        return f"[{agent.upper()}] {result}"
    except Exception as e:
        error = f"delegate: {agent} failed — {e}"
        logger.error(error, exc_info=True)
        return error


def delegate_sync(agent: str, task: str) -> str:
    """Synchronous wrapper for use in non-async contexts."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an async context — can't use run()
            # Create a new thread with its own event loop
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, delegate(agent, task))
                return future.result(timeout=120)
        else:
            return loop.run_until_complete(delegate(agent, task))
    except Exception as e:
        return f"delegate_sync error: {e}"


def list_agents() -> str:
    """Returns a formatted list of all agents and what they do."""
    lines = ["**Available Sub-Agents:**\n"]
    for name, desc in AGENT_DESCRIPTIONS.items():
        lines.append(f"• **{name}** — {desc}")
    return "\n".join(lines)
