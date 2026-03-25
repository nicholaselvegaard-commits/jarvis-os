"""
Simple JSON-based CRM. Stores customers, contacts, pipeline stages, and notes.
For production scale, migrate to Supabase via tools/supabase.py.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CRM_FILE = Path("memory/crm.json")

PIPELINE_STAGES = ["lead", "contacted", "demo", "proposal", "negotiation", "closed_won", "closed_lost"]


def _load() -> dict:
    if CRM_FILE.exists():
        try:
            return json.loads(CRM_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            logger.warning("crm.json corrupt — resetting")
    return {"customers": {}, "contacts": {}}


def _save(data: dict) -> None:
    CRM_FILE.parent.mkdir(parents=True, exist_ok=True)
    CRM_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def add_customer(
    name: str,
    email: str = "",
    phone: str = "",
    company: str = "",
    stage: str = "lead",
    notes: str = "",
    monthly_value: float = 0.0,
) -> str:
    """
    Add a new customer/lead to the CRM.

    Returns:
        Customer ID
    """
    data = _load()
    cid = str(uuid.uuid4())[:8]
    data["customers"][cid] = {
        "id": cid,
        "name": name,
        "email": email,
        "phone": phone,
        "company": company,
        "stage": stage,
        "notes": [{"text": notes, "date": _now()}] if notes else [],
        "monthly_value": monthly_value,
        "created_at": _now(),
        "updated_at": _now(),
    }
    _save(data)
    logger.info(f"CRM: added customer {name} (ID: {cid})")
    return cid


def update_stage(customer_id: str, stage: str) -> str:
    """Move a customer to a different pipeline stage."""
    if stage not in PIPELINE_STAGES:
        raise ValueError(f"Invalid stage: {stage}. Valid: {PIPELINE_STAGES}")
    data = _load()
    if customer_id not in data["customers"]:
        raise KeyError(f"Customer {customer_id} not found")
    data["customers"][customer_id]["stage"] = stage
    data["customers"][customer_id]["updated_at"] = _now()
    _save(data)
    return f"Customer {customer_id} moved to stage: {stage}"


def add_note(customer_id: str, note: str) -> None:
    """Add a note to a customer record."""
    data = _load()
    if customer_id not in data["customers"]:
        raise KeyError(f"Customer {customer_id} not found")
    data["customers"][customer_id]["notes"].append({"text": note, "date": _now()})
    data["customers"][customer_id]["updated_at"] = _now()
    _save(data)


def get_customer(customer_id: str) -> dict:
    """Return full customer record."""
    return _load()["customers"].get(customer_id, {})


def list_by_stage(stage: str) -> list[dict]:
    """Return all customers in a given pipeline stage."""
    return [c for c in _load()["customers"].values() if c["stage"] == stage]


def get_pipeline_summary() -> str:
    """Return a human-readable pipeline summary."""
    data = _load()
    customers = data["customers"].values()
    lines = ["*CRM Pipeline*"]
    for stage in PIPELINE_STAGES:
        in_stage = [c for c in customers if c["stage"] == stage]
        if in_stage:
            total = sum(c.get("monthly_value", 0) for c in in_stage)
            lines.append(f"  {stage}: {len(in_stage)} ({total:,.0f}kr/mnd)")
    return "\n".join(lines)


def search(query: str) -> list[dict]:
    """Search customers by name, email, or company."""
    q = query.lower()
    return [
        c for c in _load()["customers"].values()
        if q in c.get("name", "").lower()
        or q in c.get("email", "").lower()
        or q in c.get("company", "").lower()
    ]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Lead Scoring & Pipeline ──────────────────────────────────────────────────

_SENIOR_TITLES = {"ceo", "founder", "daglig leder", "owner", "co-founder", "direktør", "managing director"}
_EUROPEAN_COUNTRIES = {
    "norway", "sweden", "denmark", "finland", "germany", "netherlands",
    "france", "spain", "italy", "poland", "austria", "switzerland",
    "belgium", "portugal", "czech republic", "hungary", "romania",
    "slovakia", "croatia", "slovenia", "estonia", "latvia", "lithuania",
    "luxembourg", "ireland", "greece", "bulgaria",
}


def score_lead(lead: dict) -> int:
    """
    Score a lead 0-100 based on data quality and fit.

    Scoring:
    +30  has email
    +20  company has 10-500 employees (sweet spot)
    +15  title is CEO/Founder/Daglig leder/Owner
    +10  country is Norway or is European
    +10  has LinkedIn URL
    +10  has phone number
    +5   company has website
    """
    score = 0

    # +30 has email
    if lead.get("email", "").strip():
        score += 30

    # +20 company has 10-500 employees
    employees = lead.get("employees") or lead.get("company_employees") or 0
    try:
        employees = int(employees)
    except (TypeError, ValueError):
        employees = 0
    if 10 <= employees <= 500:
        score += 20

    # +15 title is senior / decision-maker
    title = (lead.get("title") or lead.get("job_title") or "").lower()
    if any(t in title for t in _SENIOR_TITLES):
        score += 15

    # +10 country is Norway or European
    country = (lead.get("country") or "").lower().strip()
    if country in ("norway", "norge", "no"):
        score += 10
    elif country in _EUROPEAN_COUNTRIES:
        score += 10

    # +10 has LinkedIn URL
    linkedin = lead.get("linkedin_url") or lead.get("linkedin") or ""
    if str(linkedin).strip():
        score += 10

    # +10 has phone number
    if lead.get("phone", "").strip():
        score += 10

    # +5 company has website
    website = lead.get("website") or lead.get("company_website") or ""
    if str(website).strip():
        score += 5

    return min(score, 100)


def get_hot_leads(min_score: int = 70) -> list[dict]:
    """Return leads with score >= min_score that haven't been contacted yet."""
    data = _load()
    hot: list[dict] = []
    for customer in data["customers"].values():
        if customer.get("stage") != "lead":
            continue
        s = score_lead(customer)
        if s >= min_score:
            hot.append({**customer, "score": s})
    hot.sort(key=lambda c: c["score"], reverse=True)
    logger.info(f"CRM: {len(hot)} hot leads with score >= {min_score}")
    return hot


def mark_contacted(lead_id: str, channel: str, message_preview: str) -> None:
    """
    Log that a lead was contacted.
    Updates stage to 'contacted', adds note with channel + preview.
    """
    data = _load()
    if lead_id not in data["customers"]:
        raise KeyError(f"Customer {lead_id} not found")
    customer = data["customers"][lead_id]
    customer["stage"] = "contacted"
    note_text = f"[{channel.upper()}] {message_preview[:200]}"
    customer["notes"].append({"text": note_text, "date": _now()})
    customer["updated_at"] = _now()
    _save(data)
    logger.info(f"CRM: {lead_id} marked as contacted via {channel}")


def get_followup_due(days: int = 3) -> list[dict]:
    """
    Return leads in 'contacted' stage that haven't responded in `days` days.
    Check updated_at field — if more than `days` ago, they're due for follow-up.
    """
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    due: list[dict] = []
    for customer in _load()["customers"].values():
        if customer.get("stage") != "contacted":
            continue
        updated_raw = customer.get("updated_at", "")
        try:
            updated_at = datetime.fromisoformat(updated_raw)
        except (ValueError, TypeError):
            continue
        if updated_at < cutoff:
            due.append(customer)
    logger.info(f"CRM: {len(due)} leads due for follow-up (>{days} days since contact)")
    return due
