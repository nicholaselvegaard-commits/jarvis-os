"""
Agent Templates — Mal-basert spawning av nye sub-agenter.
NEXUS bruker ALLTID dette systemet. Aldri dynamisk kodekjøring.
"""

from datetime import datetime
from typing import Dict, Any

TEMPLATES: Dict[str, Dict[str, Any]] = {
    "sales_agent": {
        "description": "Selger AI-tjenester via e-post og telefon",
        "model": "claude-haiku-4-5-20251001",
        "system_prompt_template": (
            "Du er {name} — en elite salgsagent.\n"
            "Mål: {goal}\n"
            "Målgruppe: {target_audience}\n"
            "Produkt: {product}\n"
            "Tone: Profesjonell, direkte, verdifokusert. Svar på norsk."
        ),
        "required_params": ["name", "goal", "target_audience", "product"],
        "tools": ["email_tool", "mcp_board"],
    },
    "research_agent": {
        "description": "Finner leads og markedsinformasjon",
        "model": "claude-haiku-4-5-20251001",
        "system_prompt_template": (
            "Du er {name} — en research-spesialist.\n"
            "Mål: {goal}\n"
            "Fokus: {focus_area}\n"
            "Lever alltid data i strukturert format (JSON eller Markdown-tabell)."
        ),
        "required_params": ["name", "goal", "focus_area"],
        "tools": ["apollo", "research_tool", "mcp_board"],
    },
    "content_agent": {
        "description": "Lager innhold for sosiale medier og blogg",
        "model": "claude-sonnet-4-6",
        "system_prompt_template": (
            "Du er {name} — innholdsprodusent.\n"
            "Mål: {goal}\n"
            "Plattform: {platform}\n"
            "Tone: {tone}"
        ),
        "required_params": ["name", "goal", "platform", "tone"],
        "tools": ["mcp_board"],
    },
    "code_agent": {
        "description": "Skriver og vedlikeholder Python-kode",
        "model": "claude-sonnet-4-6",
        "system_prompt_template": (
            "Du er {name} — senior Python-utvikler.\n"
            "Mål: {goal}\n"
            "Spesialitet: {specialty}\n"
            "Skriv alltid ren, dokumentert og sikker kode."
        ),
        "required_params": ["name", "goal", "specialty"],
        "tools": ["mcp_board"],
    },
    "voice_agent": {
        "description": "Ringer kunder via Vapi.ai",
        "model": "claude-sonnet-4-6",
        "system_prompt_template": (
            "Du er {name} — AI-stemmeagent.\n"
            "Mål: {goal}\n"
            "OBLIGATORISK: Start ALLTID med "
            "'Hei, jeg ringer fra {company_name}, jeg heter {agent_name}'\n"
            "Script: {script}"
        ),
        "required_params": ["name", "goal", "company_name", "agent_name", "script"],
        "tools": ["voice_tool", "mcp_board"],
    },
}


def spawn_agent(template_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Lag ny agent-konfigurasjon fra mal."""
    if template_name not in TEMPLATES:
        raise ValueError(f"Ukjent mal '{template_name}'. Tilgjengelige: {list(TEMPLATES.keys())}")

    template = TEMPLATES[template_name]
    missing = [p for p in template["required_params"] if p not in params]
    if missing:
        raise ValueError(f"Manglende parametere for '{template_name}': {missing}")

    return {
        "name": params.get("name", template_name),
        "template": template_name,
        "model": template["model"],
        "system_prompt": template["system_prompt_template"].format(**params),
        "tools": template["tools"],
        "description": template["description"],
        "created_at": datetime.utcnow().isoformat(),
        "params": params,
    }


def list_templates() -> Dict[str, str]:
    return {name: t["description"] for name, t in TEMPLATES.items()}
