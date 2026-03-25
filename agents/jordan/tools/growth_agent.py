"""
GrowthAgent — Passive income and product launches.

Manages:
- Gumroad digital products (pricing, listings, promos)
- Product Hunt launches (prep + submission)
- SEO / content marketing funnels
- Stripe payment links for quick sales

Goal: Every week Jarvis has one new revenue source live.
"""
import json
import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are GrowthAgent, obsessed with recurring and passive income.

Given a growth task, respond with JSON:
{
  "channel": "gumroad|producthunt|seo|stripe|other",
  "product_idea": "Specific digital product or offer (if relevant)",
  "price_point": "Suggested price in USD — use psychology: $17, $47, $97, $197",
  "launch_plan": "3-step launch plan",
  "week1_goal": "Measurable target for week 1 (e.g. 5 sales, 100 signups)",
  "action_now": "One thing Jarvis can do in the next 30 minutes"
}

Products that work for a 17-year-old AI founder:
- AI prompt packs ($17-47)
- Automation templates for Make.com / n8n ($47-97)
- "How I built X" guides ($17-37)
- Lead lists + outreach sequences ($97-197)
- Done-for-you landing pages ($297-497)

Distribution > Product. Product Hunt + Reddit + Twitter is free distribution.
"""


class GrowthAgent(BaseAgent):
    """Product launches, Gumroad, passive income. One new revenue stream/week."""

    name = "growth"
    system_prompt = _SYSTEM
    max_tokens = 1500

    async def _act(self, task: str, plan: str) -> str:
        try:
            data = json.loads(plan.strip().strip("```json").strip("```").strip())
        except Exception:
            return plan

        results = []
        channel = data.get("channel", "")
        action = data.get("action_now", "")
        product = data.get("product_idea", "")
        price = data.get("price_point", "")

        results.append(f"📦 Channel: {channel}")
        if product:
            results.append(f"💡 Product: {product} @ {price}")
        if action:
            results.append(f"⚡ Do now: {action}")

        # Create a Gumroad product draft if channel is gumroad
        if channel == "gumroad":
            try:
                from pathlib import Path
                import json as j
                draft = Path("outputs/gumroad_drafts.json")
                draft.parent.mkdir(exist_ok=True)
                items = []
                if draft.exists():
                    try:
                        items = j.loads(draft.read_text())
                    except Exception:
                        pass
                items.append(data)
                draft.write_text(j.dumps(items[-10:], indent=2, ensure_ascii=False))
                results.append("💾 Gumroad draft saved → outputs/gumroad_drafts.json")
            except Exception as e:
                logger.warning(f"GrowthAgent draft save failed: {e}")

        week1 = data.get("week1_goal", "")
        if week1:
            results.append(f"🎯 Week 1 goal: {week1}")

        return "\n".join(results)
