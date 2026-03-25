"""
Platform Reporter — NEXUS brain → AIoffice Platform bridge
===========================================================
Import og kall report_activity() fra hvilken som helst agent.
Serveren: http://89.167.100.7:8091 (eller NEXUS_PLATFORM_URL env)
"""
import os, json

PLATFORM_URL = os.getenv("NEXUS_PLATFORM_URL", os.getenv("PLATFORM_URL", "http://89.167.100.7:8091"))


def _post(path: str, payload: dict) -> bool:
    """Fire-and-forget HTTP POST — bruker bare stdlib, ingen requests-dep."""
    try:
        import urllib.request
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{PLATFORM_URL}{path}", data=body,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(req, timeout=4)
        return True
    except Exception:
        return False  # Aldri krasj agenten om plattformen er nede


def report_activity(agent: str, activity: str, position: str = "desk") -> bool:
    """Rapporter hva agenten gjør til live-kontoret (vises i feed + tale-boblene)."""
    return _post("/api/activity", {"agent": agent, "activity": activity, "position": position})


def post_idea(agent: str, idea: str, category: str = "revenue") -> bool:
    """Lagre en ny idé som vises på idea-boardet i kontoret."""
    return _post("/api/ideas", {"agent": agent, "idea": idea, "category": category})


def update_kpi(emails_sent: int = 0, leads_found: int = 0,
               revenue: int = 0, tasks_done: int = 0) -> bool:
    """Push oppdaterte KPI-tall til kontor-TV-en."""
    return _post("/api/kpi", {
        "emails_sent": emails_sent,
        "leads_found": leads_found,
        "revenue": revenue,
        "tasks_done": tasks_done,
    })


def report_run_complete(run_type: str, stats: dict) -> bool:
    """Kall etter en ferdig research/sales-kjøring — oppdaterer alt."""
    msg = f"✅ {run_type.capitalize()}-kjøring ferdig | leads={stats.get('leads',0)} | epost={stats.get('emails_sent',0)}"
    report_activity("nexus", msg, "desk")
    update_kpi(
        leads_found=stats.get("leads", 0),
        emails_sent=stats.get("emails_sent", 0),
        revenue=stats.get("revenue_est", 0),
        tasks_done=stats.get("tasks_done", 0),
    )
    return True
