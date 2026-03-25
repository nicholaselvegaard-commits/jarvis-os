"""
ScoutAgent — Competitive intelligence + opportunity scanner.

Pulls news (RSS/NewsAPI) + Google Trends Norway → asks Groq to score each item
1-10 for business opportunity potential → filters > 7 → Telegram alert +
smart memory. Also ego-searches "Nicholas Elvegaard".

Usage:
    agent = ScoutAgent()
    result = await agent.run("Scan for opportunities and competitive intel")
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from agents.jordan.tools.base_agent import BaseAgent
from tools.groq_client import chat as groq_chat

logger = logging.getLogger(__name__)

# ── Groq system prompt ────────────────────────────────────────────────────────
_SYSTEM = """\
Du er ScoutAgent — etterretningssystem for en 17-årig norsk AI-gründer fra Bodø.

Gitt en liste med nyheter og trendende søk, vurder hvert element som en
forretningsmulighet for en ung norsk AI-gründer.

Svar ALLTID med et JSON-objekt og ingenting annet:
{
  "findings": [
    {
      "title": "Tittel på funn",
      "source": "kilde",
      "score": 8,
      "money_angle": "Konkret måte å tjene penger på dette innen 30 dager",
      "action": "Hva NEXUS bør gjøre I DAG",
      "confidence": "HIGH | MEDIUM | LOW"
    }
  ],
  "ego_mentions": ["...eventuelle treff på 'Nicholas Elvegaard'..."],
  "top_opportunity": "Navn på det beste funnet"
}

Regler:
- Score 1-10: 10 = umiddelbar inntektsmulighet, 1 = irrelevant hype
- Vær konkret — ingen vage påstander
- Vurder norsk markedsfokus høyt (norske bedrifter, norsk AI-regulering, norsk kapital)
- Nytt API / gratis tier / beta = potensiell fordel → gi høy score
- Ignorer generell hype uten klar pengevei
"""

# ── Ego-search keyword ────────────────────────────────────────────────────────
_EGO_QUERY = "Nicholas Elvegaard"
_HIGH_SCORE_THRESHOLD = 7


def _parse_json(raw: str) -> dict[str, Any]:
    """Strip markdown fences and parse JSON from Groq response."""
    cleaned = raw.strip()
    for fence in ("```json", "```"):
        if cleaned.startswith(fence):
            cleaned = cleaned[len(fence):]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return json.loads(cleaned.strip())


class ScoutAgent(BaseAgent):
    """
    Competitive intelligence agent.

    Fetches news + Google Trends NO → Groq scores each item → filters > 7
    → Telegram alert + smart memory save.
    """

    name = "scout"
    system_prompt = _SYSTEM
    max_tokens = 2048

    async def _act(self, task: str, plan: str) -> str:
        raw_items: list[dict[str, str]] = []

        # ── 1. Fetch news ─────────────────────────────────────────────────────
        try:
            from tools.news_fetcher import fetch_all
            news = fetch_all(limit_per_source=5)
            for item in news[:30]:
                raw_items.append({"title": item.title, "source": item.source, "url": item.url})
            logger.info(f"ScoutAgent: fetched {len(raw_items)} news items")
        except Exception as exc:
            logger.warning(f"ScoutAgent news fetch failed: {exc}")

        # ── 2. Fetch Google Trends Norway ─────────────────────────────────────
        trends_raw: list[str] = []
        try:
            from tools.google_trends import get_trending_searches
            trends_raw = get_trending_searches(geo="norway")
            for trend in trends_raw[:20]:
                raw_items.append({"title": trend, "source": "Google Trends NO", "url": ""})
            logger.info(f"ScoutAgent: {len(trends_raw)} NO trends fetched")
        except Exception as exc:
            logger.warning(f"ScoutAgent Google Trends failed: {exc}")

        # ── 3. Ego search — look for "Nicholas Elvegaard" mentions ────────────
        ego_hits: list[str] = []
        try:
            from tools.ddg_search import search as ddg_search
            ego_results = ddg_search(_EGO_QUERY)
            # ddg_search returns a formatted string; scan for the name
            if _EGO_QUERY.lower() in ego_results.lower():
                ego_hits.append(f"Possible mention found in DDG results: {ego_results[:200]}")
        except Exception as exc:
            logger.warning(f"ScoutAgent ego search failed: {exc}")

        if not raw_items:
            logger.warning("ScoutAgent: no raw items collected — returning base plan")
            return plan

        # ── 4. Ask Groq to score each item ────────────────────────────────────
        items_text = "\n".join(
            f"- [{i['source']}] {i['title']}"
            for i in raw_items[:40]
        )
        ego_text = (
            f"\nEgo-søk ('Nicholas Elvegaard') treff:\n"
            + "\n".join(f"  - {h}" for h in ego_hits)
            if ego_hits else ""
        )

        analysis_prompt = (
            f"Oppgave: {task}\n\n"
            f"Nyheter og trender:\n{items_text}"
            f"{ego_text}\n\n"
            "Score hvert element 1-10 som forretningsmulighet for en 17-årig norsk AI-gründer."
        )

        try:
            scored_raw = groq_chat(
                prompt=analysis_prompt,
                system=self.system_prompt,
                max_tokens=self.max_tokens,
                temperature=0.3,
            )
            scored_data = _parse_json(scored_raw)
        except Exception as exc:
            logger.warning(f"ScoutAgent Groq scoring failed: {exc}")
            # Fall back to unscored summary
            return f"ScoutAgent: collected {len(raw_items)} items. Groq scoring failed: {exc}"

        findings: list[dict[str, Any]] = scored_data.get("findings", [])
        top_opportunity: str = scored_data.get("top_opportunity", "")
        ego_mentions: list[str] = scored_data.get("ego_mentions", []) or ego_hits

        # ── 5. Filter high-scoring items ──────────────────────────────────────
        hot_findings = [f for f in findings if f.get("score", 0) > _HIGH_SCORE_THRESHOLD]

        results: list[str] = []
        results.append(
            f"Scanned {len(raw_items)} items, "
            f"{len(findings)} scored, "
            f"{len(hot_findings)} above threshold ({_HIGH_SCORE_THRESHOLD})"
        )

        # ── 6. Telegram alert if anything is hot ─────────────────────────────
        if hot_findings:
            try:
                from telegram_bot import notify_owner
                hot_lines = [
                    f"ScoutAgent: {len(hot_findings)} muligheter funnet!\n"
                    f"Topp: {top_opportunity}\n"
                ]
                for f in hot_findings[:5]:
                    hot_lines.append(
                        f"\n[{f.get('score', '?')}/10] {f.get('title', '')}\n"
                        f"Pengevinkel: {f.get('money_angle', '')}\n"
                        f"Handling: {f.get('action', '')}\n"
                        f"Sikkerhet: {f.get('confidence', '')}"
                    )
                if ego_mentions:
                    hot_lines.append(f"\nEgo-treff: {', '.join(ego_mentions[:3])}")
                notify_owner("\n".join(hot_lines))
                results.append("Telegram alert sent")
            except Exception as exc:
                logger.warning(f"ScoutAgent Telegram alert failed: {exc}")
                results.append(f"Telegram alert failed: {exc}")

        if ego_mentions:
            results.append(f"Ego mentions: {len(ego_mentions)} hit(s)")

        # ── 7. Save findings to smart memory ─────────────────────────────────
        try:
            from memory.smart_memory import save
            memory_content = (
                f"ScoutAgent [{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC]\n"
                f"Items scanned: {len(raw_items)} | Hot: {len(hot_findings)}\n"
                f"Top opportunity: {top_opportunity}\n"
            )
            if hot_findings:
                for f in hot_findings[:3]:
                    memory_content += (
                        f"\n- [{f.get('score')}/10] {f.get('title', '')} "
                        f"| {f.get('money_angle', '')}"
                    )
            save(
                category="insight",
                content=memory_content,
                priority=2 if hot_findings else 1,
            )
            results.append("Memory saved")
        except Exception as exc:
            logger.warning(f"ScoutAgent memory save failed: {exc}")
            results.append(f"Memory save failed: {exc}")

        summary = (
            f"ScoutAgent done. Top: {top_opportunity!r}. "
            + " | ".join(results)
        )
        logger.info(summary)
        return summary
