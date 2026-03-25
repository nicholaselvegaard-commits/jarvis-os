"""
DevAgent — Builds and deploys products for clients.

Given a brief → generates code → saves to repo → deploys to Vercel.
Uses Claude Sonnet (needs strong code quality).
Stack: React/Vite + FastAPI + Supabase + Vercel.
"""
import logging

from agents.base_agent import BaseAgent
from config.models import CLAUDE_SONNET

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are DevAgent, a senior full-stack engineer who ships fast.

Given a development task, produce:
1. A clear implementation plan (3-5 steps)
2. The actual code for the first step
3. Deployment instructions

Stack preferences:
- Frontend: React + Vite + Tailwind
- Backend: FastAPI + Python
- Database: Supabase (already configured)
- Deploy: Vercel (token available)
- Payments: Stripe (live keys available)

Write production-ready code. No TODOs. No placeholders.
Comment only where logic is non-obvious.
"""


class DevAgent(BaseAgent):
    """Builds full-stack apps and deploys them. React + FastAPI + Vercel."""

    name = "dev"
    system_prompt = _SYSTEM
    # Dev work needs Claude Sonnet — Groq not reliable enough for code
    groq_model = "llama-3.3-70b-versatile"
    max_tokens = 4096

    async def _act(self, task: str, plan: str) -> str:
        results = []

        # Save generated code to outputs/dev/
        try:
            from pathlib import Path
            from datetime import datetime
            dev_dir = Path("outputs/dev")
            dev_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            # Sanitize task for filename
            slug = "".join(c if c.isalnum() else "_" for c in task[:30]).strip("_")
            out_file = dev_dir / f"{slug}_{ts}.md"
            out_file.write_text(
                f"# Dev Task: {task}\n\n{plan}",
                encoding="utf-8",
            )
            results.append(f"💾 Code saved: {out_file.name}")
        except Exception as e:
            logger.warning(f"DevAgent save failed: {e}")

        results.append(plan[:300] + ("..." if len(plan) > 300 else ""))
        return "\n".join(results)
