"""
ContentAgent — Nicholas Elvegaard's personal brand machine.

Generates platform-native content (Twitter/X, LinkedIn, Reddit),
saves drafts locally, and sends them to Nicholas on Telegram for approval.
Nothing is auto-posted. Approval loop: 👍 post, 👎 drop.

Usage:
    agent = ContentAgent()
    result = await agent.run("Create content about AI automation trends in Norway")
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.jordan.tools.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# ── Output directory ──────────────────────────────────────────────────────────
_DRAFTS_DIR = Path("/opt/nexus/outputs/content_drafts")

# ── Groq system prompt ────────────────────────────────────────────────────────
_SYSTEM = """\
Du er ContentAgent — du bygger Nicholas Elvegaards personlige merkevare.

Nicholas er 17 år, fra Bodø, bygger et AI-imperium og er på vei til Silicon Valley.
Vinkel: yngste seriøse AI-gründer i Norge. Autentisk, ikke corporate.

Svar ALLTID med et JSON-objekt og ingenting annet:
{
  "twitter": "Tweet på maks 280 tegn. Hook i de 5 første ordene. Maks 2 hashtags.",
  "linkedin": "LinkedIn-innlegg på maks 200 ord på norsk. Format: situasjon → problem → løsning → resultat.",
  "reddit": {
    "subreddit": "r/entrepreneur eller r/artificial",
    "title": "Reddit-tittel — hjelpsom, ikke salgsy",
    "body": "Reddit-brødtekst — del innsikt, ikke selg"
  },
  "platform_priority": "twitter | linkedin | reddit"
}

Stemme: selvsikker men ikke arrogant. Spesifikk, ikke vag. Tall > adjektiver.

Godt eksempel (Twitter): "Bygget en AI som sender kalde e-poster mens jeg er på skolen. 47 e-poster i dag. 0 avvisninger."
Dårlig eksempel (Twitter): "Spent to share my AI journey! #AI #startup"

Skriv som Nicholas faktisk snakker — 17-åring fra Bodø, ikke en PR-avdeling.
"""


def _parse_json(raw: str) -> dict[str, Any]:
    """Strip markdown fences and parse JSON from Groq response."""
    cleaned = raw.strip()
    for fence in ("```json", "```"):
        if cleaned.startswith(fence):
            cleaned = cleaned[len(fence):]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return json.loads(cleaned.strip())


def _format_telegram_preview(data: dict[str, Any]) -> str:
    """Build the Telegram approval message Nicholas will see."""
    twitter = data.get("twitter", "")
    linkedin = data.get("linkedin", "")
    reddit = data.get("reddit", {})

    lines = [
        "ContentAgent har laget innhold. Godkjenn eller droppet:",
        "",
        "--- TWITTER/X ---",
        twitter or "(tomt)",
        "",
        "--- LINKEDIN ---",
        linkedin or "(tomt)",
        "",
        "--- REDDIT ---",
        f"r/{reddit.get('subreddit', 'entrepreneur')} | {reddit.get('title', '')}",
        reddit.get("body", "")[:300] + ("..." if len(reddit.get("body", "")) > 300 else ""),
        "",
        "Svar 👍 for å poste, 👎 for å droppe",
    ]
    return "\n".join(lines)


class ContentAgent(BaseAgent):
    """
    Content pipeline with Telegram approval queue.

    Generates Twitter/LinkedIn/Reddit drafts, saves them locally,
    and sends to Nicholas for manual approval. Does NOT auto-post.
    """

    name = "content"
    system_prompt = _SYSTEM
    max_tokens = 1200

    async def _act(self, task: str, plan: str) -> str:
        # ── 1. Parse Groq plan ────────────────────────────────────────────────
        try:
            data = _parse_json(plan)
        except Exception as exc:
            logger.warning(f"ContentAgent: JSON parse failed ({exc}), returning raw plan")
            return plan

        results: list[str] = []
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # ── 2. Save drafts to disk ────────────────────────────────────────────
        try:
            _DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
            draft_path = _DRAFTS_DIR / f"draft_{timestamp}.json"
            draft_payload = {
                "task": task,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "content": data,
            }
            draft_path.write_text(
                json.dumps(draft_payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            results.append(f"Draft saved: {draft_path.name}")
            logger.info(f"ContentAgent: draft written to {draft_path}")
        except Exception as exc:
            logger.warning(f"ContentAgent draft save failed: {exc}")
            results.append(f"Draft save failed: {exc}")

        # ── 3. Send Telegram approval request ────────────────────────────────
        try:
            from telegram_bot import notify_owner
            preview = _format_telegram_preview(data)
            notify_owner(preview)
            results.append("Telegram approval request sent")
        except Exception as exc:
            logger.warning(f"ContentAgent Telegram error: {exc}")
            results.append(f"Telegram not sent: {exc}")

        # ── 4. Return summary ─────────────────────────────────────────────────
        priority = data.get("platform_priority", "twitter")
        twitter_preview = (data.get("twitter") or "")[:80]

        summary = (
            f"ContentAgent: {len(results)} actions. "
            f"Priority platform: {priority}. "
            f"Twitter preview: {twitter_preview!r}. "
            + " | ".join(results)
        )
        logger.info(f"ContentAgent done: {summary}")
        return summary
