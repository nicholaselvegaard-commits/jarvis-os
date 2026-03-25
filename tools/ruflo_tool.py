"""
Ruflo Tool — Wrapper for Ruflo v3.5 MCP-plattform.

Gir NEXUS tilgang til:
  - Persistent vektorminne (memory_store / memory_search)
  - Agent-koordinering (agent_spawn / agent_list)
  - Swarm-orkestrering (swarm_init)

Alle kall går via Ruflo CLI (subprocess) siden HTTP-server ikke er konfigurert.
"""

import json
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

RUFLO_CMD = "ruflo"


def _run(args: list[str], timeout: int = 15) -> dict:
    """Kjør ruflo CLI-kommando og returner resultat."""
    import os
    env = os.environ.copy()
    env["HOME"] = "/root"  # Ruflo finner memory.db via HOME
    try:
        result = subprocess.run(
            [RUFLO_CMD] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd="/root",
            env=env,
        )
        # Prøv å parse JSON fra output (noen kommandoer returnerer JSON)
        output = result.stdout.strip()
        try:
            return json.loads(output)
        except Exception:
            return {"output": output, "error": result.stderr.strip() or None}
    except subprocess.TimeoutExpired:
        logger.error(f"Ruflo timeout: {args}")
        return {"error": "timeout"}
    except Exception as e:
        logger.error(f"Ruflo feil: {e}")
        return {"error": str(e)}


# ─── MINNE ───────────────────────────────────────────────────────────────────

def memory_store(key: str, value: str, namespace: str = "nexus", ttl: Optional[int] = None) -> bool:
    """
    Lagre et faktum/resultat i Ruflos persistente vektorminne.

    Namespace settes som key-prefiks: "nexus:lead:xxx", "nexus:campaign:xxx".
    Args:
        key:       Nøkkel — vil automatisk få "nexus:" prefiks hvis ikke allerede satt
        value:     Innhold (tekst)
        namespace: Ignoreres (Ruflo bruker key-prefiks for navnerom)
        ttl:       Levetid i sekunder (None = permanent)
    """
    full_key = key if key.startswith("nexus:") else f"nexus:{key}"
    args = ["memory", "store", "-k", full_key, "-v", value]
    if ttl:
        args += ["--ttl", str(ttl)]
    result = _run(args)
    # Suksess: output inneholder "stored successfully" eller ingen error-linje
    output = result.get("output", "")
    ok = "stored successfully" in output or ("error" not in result)
    if ok:
        logger.info(f"Ruflo memory stored: {full_key}")
    else:
        logger.warning(f"Ruflo memory store feil: {result}")
    return ok


def memory_retrieve(key: str, namespace: str = "nexus") -> Optional[str]:
    """Hent en spesifikk verdi fra minnet."""
    full_key = key if key.startswith("nexus:") else f"nexus:{key}"
    result = _run(["memory", "retrieve", "-k", full_key])
    value = result.get("value") or result.get("output")
    return value if value else None


def memory_search(query: str, namespace: str = "nexus", limit: int = 5) -> list[dict]:
    """
    Semantisk vektorsøk i Ruflos minne (HNSW-vektorer, 384-dim).

    Args:
        query:  Naturlig språk (f.eks. "leads i regnskap med høy score")
        limit:  Maks antall treff

    Returns:
        Liste med dicts: [{key, score, value}, ...]
    """
    result = _run(["memory", "search", "--query", query, "--limit", str(limit)])
    if isinstance(result, list):
        return result
    if "results" in result:
        return result["results"]

    # Parse table output fra ruflo CLI
    output = result.get("output", "")
    entries = []
    for line in output.split("\n"):
        # Tabell-rader: | key | score | namespace | preview |
        if line.startswith("| nexus:") or line.startswith("| nexus_"):
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 4:
                entries.append({
                    "key":   parts[0],
                    "score": parts[1],
                    "value": parts[3],
                })
    return entries


def memory_list(namespace: str = "nexus", limit: int = 20) -> list[dict]:
    """List nøkler i NEXUS namespace."""
    result = _run(["memory", "list", "--limit", str(limit)])
    if isinstance(result, list):
        return result
    return []


# ─── AGENT-KOORDINERING ───────────────────────────────────────────────────────

def agent_spawn(name: str, role: str, goal: str) -> dict:
    """
    Spawn en ny sub-agent via Ruflos agent pool.

    Args:
        name:  Agentens navn (f.eks. "lead-scorer-1")
        role:  Rolle (f.eks. "researcher", "sales", "coder")
        goal:  Hva agenten skal gjøre

    Returns:
        {"agent_id": "...", "status": "spawned"} eller {"error": "..."}
    """
    payload = json.dumps({"name": name, "role": role, "goal": goal, "type": "worker"})
    result = _run(["mcp", "exec", "--tool", "agent_spawn", "--input", payload])
    logger.info(f"Ruflo agent spawned: {name} ({role})")
    return result


def agent_list() -> list[dict]:
    """List alle aktive agenter i Ruflo agent pool."""
    result = _run(["mcp", "exec", "--tool", "agent_list", "--input", "{}"])
    if isinstance(result, list):
        return result
    return result.get("agents", [])


def agent_status(agent_id: str) -> dict:
    """Sjekk status på en spesifikk agent."""
    payload = json.dumps({"agent_id": agent_id})
    return _run(["mcp", "exec", "--tool", "agent_status", "--input", payload])


# ─── SWARM ────────────────────────────────────────────────────────────────────

def swarm_init(name: str, topology: str = "hierarchical", max_agents: int = 5) -> dict:
    """
    Initialiser en Ruflo swarm for parallell oppgaveløsing.

    Topologier: hierarchical | mesh | ring | star | hybrid
    """
    payload = json.dumps({
        "name": name,
        "topology": topology,
        "maxAgents": max_agents,
        "consensus": "majority",
    })
    result = _run(["mcp", "exec", "--tool", "swarm_init", "--input", payload])
    logger.info(f"Ruflo swarm init: {name} ({topology}, max={max_agents})")
    return result


# ─── KONVENIENS-WRAPPER FOR NEXUS ─────────────────────────────────────────────

def store_lead_result(lead_id: str, company: str, score: int, observation: str, action: str):
    """
    Lagre lead-resultat for fremtidig referanse og læring.

    Eksempel:
        store_lead_result("apollo_12345", "Acme AS", 9,
            "Bruker manuell faktura, CEO aktiv på LinkedIn",
            "cold_email_sent")
    """
    value = (
        f"Bedrift: {company} | Score: {score}/10 | "
        f"Observasjon: {observation} | Handling: {action}"
    )
    return memory_store(f"lead:{lead_id}", value)


def store_campaign_stats(date: str, emails_sent: int, leads_scored: int,
                         revenue: float, top_insight: str):
    """Lagre dagens kampanjeresultater for reflexion og trend-analyse."""
    value = (
        f"Dato: {date} | E-poster: {emails_sent} | Leads scoret: {leads_scored} | "
        f"Inntekt: {revenue} NOK | Innsikt: {top_insight}"
    )
    return memory_store(f"campaign:stats:{date}", value)


def search_similar_leads(query: str, limit: int = 5) -> list[dict]:
    """
    Finn lignende leads fra tidligere kampanjer.

    Brukes av research_agent for å unngå å kontakte samme bedrift to ganger
    og for å lære av hvilke leads som konverterte.
    """
    return memory_search(f"lead: {query}", limit=limit)


def get_memory_stats() -> dict:
    """Hent statistikk over NEXUS sitt minne i Ruflo."""
    return _run(["memory", "stats"])
