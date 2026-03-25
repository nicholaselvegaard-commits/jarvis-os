"""
ResearchAgent — Deep research engine.

Uses Brave + Tavily + NewsAPI to gather raw data, then Groq to synthesize.
Returns structured Markdown summaries. Feeds SalesAgent, FinanceAgent, ScoutAgent.
"""
import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are ResearchAgent, a world-class research analyst.

Given a research task, produce a structured Markdown report:

## Summary
2-3 sentence executive summary.

## Key Facts
- Bullet list of the most important findings

## Opportunity
What money-making angle exists here? Be specific.

## Sources
List what types of sources support this (news, web, academic)

Keep it under 400 words. Be factual. Flag uncertainty with "(unconfirmed)".
"""


class ResearchAgent(BaseAgent):
    """Deep web research → structured Markdown reports. Feeds all other agents."""

    name = "research"
    system_prompt = _SYSTEM
    max_tokens = 2048

    async def _act(self, task: str, plan: str) -> str:
        # Enrich with real web data first, then re-synthesize
        web_data = []

        try:
            from tools.web_search import search
            results = search(task, max_results=5)
            web_data.extend([f"- {r.get('title','')}: {r.get('snippet','')}" for r in results[:5]])
        except Exception as e:
            logger.warning(f"ResearchAgent web search failed: {e}")

        try:
            from tools.news_fetcher import fetch_all
            news = fetch_all(limit_per_source=3)
            relevant = [n for n in news if any(w.lower() in n.title.lower() for w in task.split()[:4])]
            web_data.extend([f"- {n.title}" for n in relevant[:3]])
        except Exception as e:
            logger.warning(f"ResearchAgent news fetch failed: {e}")

        if web_data:
            # Re-ask Groq with actual data
            enriched_task = f"{task}\n\nReal data found:\n" + "\n".join(web_data[:10])
            try:
                from tools.groq_client import chat
                plan = chat(
                    prompt=enriched_task,
                    system=self.system_prompt,
                    max_tokens=self.max_tokens,
                    temperature=0.3,
                )
            except Exception as e:
                logger.warning(f"Re-synthesis failed: {e}")

        return plan
