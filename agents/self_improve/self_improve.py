"""
Jarvis Self-Improvement Loop.

Kjøres daglig (23:30) etter finanslogg.
Analyserer feil, oppdaterer strategier, lagrer lærdommer i brain.
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv("/opt/nexus/.env")
sys.path.insert(0, "/opt/nexus")

logger = logging.getLogger(__name__)
NEXUS_DIR = Path("/opt/nexus")


def _collect_todays_logs() -> str:
    """Hent feil og hendelser fra dagens logger."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_sections = []

    for log_file in ["logs/nexus.log", "logs/scheduler.log", "logs/brain_cloud.log"]:
        path = NEXUS_DIR / log_file
        if not path.exists():
            continue
        lines = path.read_text(errors="ignore").splitlines()
        # Kun dagens linjer, kun feil/viktige hendelser
        relevant = [
            l for l in lines
            if today in l and any(kw in l.upper() for kw in ["ERROR", "FAIL", "FEIL", "WARNING", "OK", "FERDIG"])
        ]
        if relevant:
            log_sections.append(f"=== {log_file} ===\n" + "\n".join(relevant[-20:]))

    return "\n\n".join(log_sections)[:3000] if log_sections else "Ingen relevante logglinjer."


def _count_kg_activity() -> dict:
    """Tell opp KG-aktivitet fra i dag."""
    try:
        from memory.brain import Brain
        b = Brain()
        status = b.status()
        return {
            "kg_nodes": status.get("knowledge_graph", {}).get("nodes", 0),
            "kg_edges": status.get("knowledge_graph", {}).get("edges", 0),
            "vector_count": status.get("vector_memory", {}).get("count", 0),
            "vault_notes": status.get("obsidian", {}).get("total_notes", 0),
        }
    except Exception:
        return {}


def run_self_improvement() -> dict:
    """
    Kjør daglig selvforbedring:
    1. Les loggene
    2. Analyser hva som gikk bra/dårlig
    3. Ekstraher lærdommer
    4. Lagre i brain
    5. Foreslå prompt-endringer
    """
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

    logs = _collect_todays_logs()
    kg_stats = _count_kg_activity()

    analysis_prompt = f"""Du er Jarvis sin selvforbedringssystem.

Analyser dagens aktivitet og trekk ut lærdommer.

LOGGER:
{logs}

KG STATISTIKK:
{json.dumps(kg_stats, indent=2)}

Svar med JSON:
{{
  "summary": "Én setning om dagens drift",
  "wins": ["hva gikk bra"],
  "problems": ["hva feilet og hvorfor"],
  "lessons": ["konkrete lærdommer for fremtiden"],
  "prompt_additions": ["setninger som bør legges til Jarvis sin system prompt"],
  "score": 7
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": analysis_prompt}],
        )

        import re
        text = response.content[0].text
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            return {"error": "Ingen JSON i respons"}

        result = json.loads(match.group())

        # Lagre lærdommer i brain
        try:
            from memory.brain import Brain
            b = Brain()
            for lesson in result.get("lessons", []):
                b.remember(
                    lesson,
                    category="learning",
                    tags=["selvforbedring", datetime.now().strftime("%Y-%m-%d")],
                    importance=2,
                )

            # Daglig notat i Obsidian
            if b.obsidian:
                note = (
                    f"\n## Selvforbedring {datetime.now().strftime('%H:%M')}\n"
                    f"**Score**: {result.get('score', '?')}/10\n"
                    f"**Oppsummering**: {result.get('summary', '')}\n\n"
                    f"**Vant**: {chr(10).join('- ' + w for w in result.get('wins', []))}\n\n"
                    f"**Problemer**: {chr(10).join('- ' + p for p in result.get('problems', []))}\n\n"
                    f"**Lærdommer**: {chr(10).join('- ' + l for l in result.get('lessons', []))}\n"
                )
                b.obsidian.daily_note(note)
        except Exception as e:
            logger.error(f"Brain lagring feil: {e}")

        # Oppdater system prompt hvis det er gode tillegg
        prompt_adds = result.get("prompt_additions", [])
        if prompt_adds:
            _append_to_prompt(prompt_adds)

        logger.info(f"Selvforbedring: score={result.get('score')}, {len(result.get('lessons',[]))} lærdommer")
        return result

    except Exception as e:
        logger.error(f"Selvforbedring feil: {e}")
        return {"error": str(e)}


def _append_to_prompt(additions: list):
    """Legg til nye regler i Jarvis sin system prompt."""
    prompt_path = NEXUS_DIR / "agents" / "jordan" / "system_prompt.txt"
    if not prompt_path.exists():
        return

    today = datetime.now().strftime("%Y-%m-%d")
    section = f"\n\n═══ LÆRDOM {today} ═══\n"
    for add in additions[:5]:  # Maks 5 nye regler per dag
        section += f"- {add}\n"

    current = prompt_path.read_text(encoding="utf-8")
    # Unngå duplikater
    if today in current:
        return

    prompt_path.write_text(current + section, encoding="utf-8")
    logger.info(f"System prompt oppdatert med {len(additions)} nye regler")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
    print("Kjører selvforbedring...")
    result = run_self_improvement()
    print(json.dumps(result, indent=2, ensure_ascii=False))
