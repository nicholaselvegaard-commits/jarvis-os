"""
AgentArchitect — designs and generates new specialized agent prompt templates.

Job: Given a need or domain, produces a complete agent spec:
- System prompt (role, personality, goals)
- Tool list (what Python tools it needs)
- Trigger conditions (when Jarvis should use it)
- Output format (what it returns)
- Saves the new agent spec to outputs/agent_specs/ for review

Jarvis delegates to this when a task falls outside existing agents
or when Nicholas asks for a new agent to be designed.
"""
import logging
from pathlib import Path
from datetime import datetime, timezone

from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are AgentArchitect — the master designer of AI sub-agents for Nicholas Elvegård's empire.

Your job: Design complete, production-ready agent specifications.

Nicholas is 17, based in Bodø, Norway. His goals:
- Autonomous income (sales, crypto, content, SaaS)
- Silicon Valley ambitions
- Replace manual work with agents
- Each agent must make or save money, or create leverage

When given a domain or need, you output a FULL agent spec in this exact format:

=== AGENT SPEC: [AGENT NAME] ===

**Role**: One sentence — what this agent IS
**Personality**: Tone, style, how it communicates results
**Primary Goal**: What money/value it creates

**System Prompt**:
[Full system prompt — 150-300 words, specific, opinionated, not generic]

**Tools Needed**:
- tool_name: why it needs it
[list all Python tools from tools/ it should use]

**Trigger Conditions**:
- [When Jarvis should delegate to this agent]
- [What keywords or situations activate it]

**Output Format**:
[Exact JSON or Markdown format the agent returns]

**Scheduler**: [Cron expression if it runs autonomously, else "On-demand"]

**KPIs**: [How to measure if this agent is doing its job]

**Example Task**: "[Example of what you'd ask this agent to do]"

Rules:
- Always use Groq (free) as default model
- Always log to agent_logger
- Never hardcode secrets — use os.getenv()
- Output must be immediately actionable by a developer
- Think like a CTO, not a product manager — be specific about implementation
"""


class AgentArchitectAgent(BaseAgent):
    """Designs complete prompt templates and specs for new AI sub-agents."""

    name = "architect"
    system_prompt = _SYSTEM
    groq_model = "llama-3.3-70b-versatile"
    max_tokens = 3000

    async def _act(self, task: str, plan: str) -> str:
        """Save the agent spec to outputs/agent_specs/ for review."""
        out_dir = Path("outputs/agent_specs")
        out_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        # Extract agent name from spec if possible
        agent_name = "unknown"
        for line in plan.splitlines():
            if line.startswith("=== AGENT SPEC:"):
                agent_name = (
                    line.replace("=== AGENT SPEC:", "")
                    .replace("===", "")
                    .strip()
                    .lower()
                    .replace(" ", "_")
                )
                break

        filename = out_dir / f"{timestamp}_{agent_name}.md"
        filename.write_text(plan, encoding="utf-8")
        logger.info(f"[architect] Saved spec to {filename}")

        return f"Agent spec saved to {filename}\n\n{plan[:800]}"
