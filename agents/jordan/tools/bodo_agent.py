"""
BodøAgent — Norwegian/Bodø market specialist.

Expert in:
- Local Bodø businesses (from Brreg + bodø_market.md)
- Norwegian regulatory landscape (ENK, AS, MVA)
- Nordic AI market pricing and positioning
- Ryde + LystPå ecosystem opportunities

Nicholas's home turf advantage. Every Silicon Valley founder needs a base.
"""
import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_SYSTEM = """\
Du er BodøAgent — ekspert på Bodø-markedet og norsk forretningsliv.

Du kjenner:
- Alle større bedrifter i Bodø (Brreg-data)
- Norsk MVA, ENK, AS, arbeidsliv
- Lokale priser (hva norske SMBer betaler for digitale tjenester)
- Ryde (elektrisk sparkesykkel) og LystPå (lokal forbruker)
- Nordnorsk mentalitet: ærlighet og konkrete resultater, ikke fluff

Gitt en oppgave, svar med:
- ANALYSE: hva du vet om dette lokale markedet
- PRIS: hva norske bedrifter realistisk betaler for AI-tjenester
- INNGANG: beste måte å nå disse bedriftene (kaldt = direkte, ikke LinkedIn-spam)
- PITCH: norsk pitch, 2 setninger, direkte og konkret
- LEADS: navn på 2-3 spesifikke Bodø-bedrifter som passer

Husk: Nicholas har jobberfaring fra Ryde og LystPå — bruk det som sosial proof.
"""


class BodoAgent(BaseAgent):
    """Norwegian/Bodø market specialist. Local leads + Norwegian pricing."""

    name = "bodo"
    system_prompt = _SYSTEM
    max_tokens = 1500

    async def _act(self, task: str, plan: str) -> str:
        context = []

        # Pull fresh Bodø leads from Brreg
        try:
            from tools.lead_agent import find_leads_brreg
            leads = find_leads_brreg(municipality="Bodø", limit=5)
            if leads:
                context.extend([f"- {l.name} | {l.industry}" for l in leads[:5]])
        except Exception as e:
            logger.warning(f"BodøAgent Brreg failed: {e}")

        # Load Bodø market knowledge
        try:
            from pathlib import Path
            kb = Path("knowledge/bodø_market.md")
            if kb.exists():
                context.append("\nMarked-kunnskap:\n" + kb.read_text(encoding="utf-8")[:800])
        except Exception:
            pass

        if context:
            enriched = f"{task}\n\nLokal kontekst:\n" + "\n".join(context)
            try:
                from tools.groq_client import chat
                plan = chat(
                    prompt=enriched,
                    system=self.system_prompt,
                    max_tokens=self.max_tokens,
                    temperature=0.4,
                )
            except Exception:
                pass

        return plan
