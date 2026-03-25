"""
EmailAgent — Manages Jarvis's inbox (jordan.develepor@outlook.com).

Reads incoming emails, classifies them (lead / reply / spam / vendor),
drafts responses, and sends autonomously for non-sensitive threads.
"""
import json
import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are EmailAgent, managing Jarvis's business email inbox.

Given email content or an instruction, respond with JSON:
{
  "classification": "lead|reply|spam|vendor|other",
  "priority": "high|medium|low",
  "summary": "One sentence what this email is about",
  "action": "reply|archive|forward_to_nicholas|ignore",
  "reply_draft": "Draft reply if action is 'reply'. Professional but direct. Max 100 words.",
  "forward_reason": "Why Nicholas needs to see this (only if action is forward_to_nicholas)"
}

Rules:
- Leads (someone asking about services) → reply with value prop + calendar link
- Replies to Jarvis's pitches → reply fast, move towards call/payment
- Spam → archive, never reply
- Vendor/sales emails → archive
- Legal, payment, contracts → forward_to_nicholas ALWAYS
"""


class EmailAgent(BaseAgent):
    """Reads Jarvis's inbox, classifies emails, responds autonomously."""

    name = "email"
    system_prompt = _SYSTEM
    max_tokens = 1024

    async def _act(self, task: str, plan: str) -> str:
        try:
            data = json.loads(plan.strip().strip("```json").strip("```").strip())
        except Exception:
            return plan

        action = data.get("action", "")
        classification = data.get("classification", "?")
        summary = data.get("summary", "")
        results = []

        results.append(f"📧 [{classification.upper()}] {summary}")

        if action == "reply" and data.get("reply_draft"):
            # Auto-reply for non-sensitive emails
            try:
                # Note: would need to extract original sender from task context
                # For now, log the draft for Jarvis to send
                from pathlib import Path
                Path("memory/email_drafts.json").parent.mkdir(exist_ok=True)
                import json as j
                drafts_file = Path("memory/email_drafts.json")
                drafts = []
                if drafts_file.exists():
                    try:
                        drafts = j.loads(drafts_file.read_text())
                    except Exception:
                        pass
                drafts.append(data)
                drafts_file.write_text(j.dumps(drafts[-20:], indent=2, ensure_ascii=False))
                results.append(f"💬 Reply drafted: {data['reply_draft'][:80]}...")
            except Exception as e:
                logger.warning(f"EmailAgent draft save failed: {e}")

        elif action == "forward_to_nicholas":
            results.append(f"⚠️ FORWARD TO NICHOLAS: {data.get('forward_reason', '')}")

        return " | ".join(results)
