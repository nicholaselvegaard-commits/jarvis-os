"""
NEXUS Lead Pipeline — Automatisert daglig lead-generering.

Kjøres av scheduler kl. 06:00 og 13:00:
  1. Søk Brreg etter IT/tech-bedrifter i norske byer
  2. Score leads basert på størrelse og relevans
  3. Lagre i KG + Obsidian vault
  4. Kø outreach-e-poster for kvalifiserte leads (score >= 6)
  5. Rapporter til Nicholas via Telegram
"""

import os
import sys
import logging
import time
from pathlib import Path
from datetime import datetime

# Sørg for at /opt/nexus er i path
_NEXUS = Path("/opt/nexus")
if str(_NEXUS) not in sys.path:
    sys.path.insert(0, str(_NEXUS))

logger = logging.getLogger("nexus.lead_pipeline")

# ── Byer og NACE-koder for IT-bedrifter ───────────────────────────────────────
TARGET_CITIES = [
    "Bodø", "Oslo", "Tromsø", "Trondheim", "Bergen",
    "Stavanger", "Kristiansand", "Drammen",
]

# NACE-koder for IT/tech-sektorer
IT_NACE_CODES = ["62", "63", "58", "73"]  # IT-tjenester, informasjonstj., forlag, reklame

# Kommunekoder (brukes av Brreg API)
KOMMUNE_KODER = {
    "Bodø": "1804", "Oslo": "0301", "Tromsø": "5401", "Trondheim": "5001",
    "Bergen": "4601", "Stavanger": "1103", "Kristiansand": "4204", "Drammen": "3005",
}

# ── Lead-scoring ───────────────────────────────────────────────────────────────

def score_lead(company: dict) -> int:
    """
    Score 1-10 basert på:
    - Antall ansatte (5-50 = sweet spot for IT-konsulting)
    - Næringsgruppe (62.xxx = høyest)
    - Har hjemmeside
    - Har e-post
    """
    score = 3  # Basis

    employees = company.get("employees") or 0
    if 5 <= employees <= 20:
        score += 3
    elif 21 <= employees <= 50:
        score += 2
    elif 51 <= employees <= 100:
        score += 1

    nace = str(company.get("nace", ""))
    if nace.startswith("62"):
        score += 2
    elif nace.startswith("63") or nace.startswith("73"):
        score += 1

    if company.get("website"):
        score += 1
    if company.get("email"):
        score += 1

    return min(score, 10)


# ── Outreach-mal ───────────────────────────────────────────────────────────────

def draft_email(company: dict, score: int) -> dict:
    """Generer personalisert e-post basert på bedriftsprofil."""
    name = company.get("name", "Hei")
    city = company.get("city", "Norge")
    employees = company.get("employees") or "?"
    nace = company.get("nace", "")

    if nace.startswith("62"):
        service_angle = "AI-automatisering og agent-systemer"
        value_prop = "frigjør tid fra repetitive oppgaver og skalerer kapasitet uten å ansette"
    elif nace.startswith("73"):
        service_angle = "AI-drevet innholdsoptimalisering"
        value_prop = "øker konverteringer og reduserer produksjonstid med 60%"
    else:
        service_angle = "AI-agenter og automasjon"
        value_prop = "automatiserer manuelle prosesser og gir konkret ROI fra dag én"

    subject = f"AI-agenter for {name} — konkret ROI på 30 dager"

    body = f"""Hei,

Jeg så at {name} jobber med {service_angle.lower()} i {city}.

Vi har hjulpet lignende bedrifter ({employees} ansatte) med å implementere AI-agenter som {value_prop}.

Konkret: én agent erstatter typisk 2-4 timer manuelt arbeid per dag.

Har du 20 minutter for en rask demo denne uken?

Mvh
Nicholas Elvegaard
AIDN AS | Bodø
"""

    return {
        "to_company": name,
        "subject": subject,
        "body": body,
        "score": score,
        "org_number": company.get("org_number", ""),
        "city": city,
    }


# ── Hoved-pipeline ────────────────────────────────────────────────────────────

def run_lead_pipeline(
    cities: list = None,
    nace_codes: list = None,
    min_score: int = 6,
    max_leads_per_run: int = 30,
    dry_run: bool = False,
) -> dict:
    """
    Kjør full lead-pipeline.

    Args:
        cities: Byer å søke i (default: TARGET_CITIES)
        nace_codes: NACE-koder (default: IT_NACE_CODES)
        min_score: Minimum score for outreach (default: 6)
        max_leads_per_run: Maks leads totalt (default: 30)
        dry_run: Hvis True, send ikke e-poster
    """
    start = time.time()
    cities = cities or TARGET_CITIES
    nace_codes = nace_codes or IT_NACE_CODES

    stats = {
        "found": 0,
        "new": 0,
        "scored": 0,
        "qualified": 0,
        "emails_queued": 0,
        "errors": [],
        "top_leads": [],
    }

    # Importer brain og tools
    try:
        from memory.brain import Brain
        brain = Brain()
    except Exception as e:
        logger.error(f"Brain import feil: {e}")
        brain = None

    try:
        from tools.brreg import find_leads as brreg_find_leads
    except Exception as e:
        logger.error(f"Brreg import feil: {e}")
        return {**stats, "error": str(e)}

    all_companies = []

    # Søk per by og NACE-kode
    for city in cities:
        for nace in nace_codes:
            try:
                results = brreg_find_leads(
                    industry_code=nace,
                    municipality=city.upper(),
                    min_employees=3,
                    max_employees=100,
                    max_results=10,
                )
                for r in results:
                    r["nace"] = r.get("industry_code", nace)
                    r["search_city"] = city
                all_companies.extend(results)
                logger.info(f"  {city}/{nace}: {len(results)} bedrifter")
            except Exception as e:
                err = f"Brreg {city}/{nace}: {e}"
                logger.warning(err)
                stats["errors"].append(err)

        if len(all_companies) >= max_leads_per_run:
            break

    stats["found"] = len(all_companies)
    logger.info(f"Pipeline: {len(all_companies)} bedrifter funnet totalt")

    # Dedupliser på org_number
    seen_orgs = set()
    unique_companies = []
    for c in all_companies:
        org = c.get("org_number") or c.get("organisasjonsnummer") or ""
        if org and org not in seen_orgs:
            seen_orgs.add(org)
            unique_companies.append(c)
    all_companies = unique_companies[:max_leads_per_run]

    # Sjekk om allerede i KG (unngå duplikater)
    known_orgs = set()
    if brain and brain.kg:
        try:
            existing = brain.kg.search_nodes("", type="company", limit=500)
            for n in existing:
                attrs = n.get("attrs", {})
                if attrs.get("org_number"):
                    known_orgs.add(str(attrs["org_number"]))
        except Exception:
            pass

    qualified_leads = []

    for company in all_companies:
        org = str(company.get("org_number") or "")

        # Hopp over allerede kjente
        if org and org in known_orgs:
            continue

        stats["new"] += 1
        score = score_lead(company)
        stats["scored"] += 1

        company_name = company.get("name") or company.get("navn") or "Ukjent"
        city = company.get("municipality") or company.get("search_city") or "?"
        employees = company.get("employees") or 0
        nace = company.get("industry_code") or company.get("nace", "")

        # Lagre i brain KG
        if brain:
            try:
                node_id = f"company_{org}" if org else f"company_{company_name.lower().replace(' ', '_')}"
                brain.kg.add_node(
                    node_id=node_id,
                    label=company_name,
                    type="company",
                    importance=min(score // 3, 3),
                    attrs={
                        "org_number": org,
                        "city": city,
                        "employees": employees,
                        "nace": nace,
                        "score": score,
                        "found_date": datetime.now().isoformat()[:10],
                        "website": company.get("website", ""),
                    }
                )
                # Relater til nicholas
                brain.kg.add_edge(node_id, "nicholas", "target_lead")
                known_orgs.add(org)
            except Exception as e:
                logger.warning(f"KG add_node feil ({company_name}): {e}")

        # Lagre i vektorminne
        if brain:
            try:
                summary = (
                    f"{company_name} er en bedrift i {city} med {employees} ansatte. "
                    f"NACE: {nace}. Lead-score: {score}/10."
                )
                brain.remember(summary, category="lead", tags=["brreg", city.lower(), nace])
            except Exception:
                pass

        # Obsidian-notat for score >= 6
        if score >= 6 and brain and brain.obsidian:
            try:
                note_id = f"Kunder/{company_name.replace(' ', '-')}"
                note_content = (
                    f"# {company_name}\n\n"
                    f"**Score**: {score}/10\n"
                    f"**By**: {city}\n"
                    f"**Ansatte**: {employees}\n"
                    f"**Org.nr**: {org}\n"
                    f"**NACE**: {nace}\n"
                    f"**Funnet**: {datetime.now().isoformat()[:10]}\n\n"
                    f"## Status\n- [ ] Outreach sendt\n- [ ] Svar mottatt\n- [ ] Demo booket\n\n"
                    f"## Notater\n"
                )
                brain.obsidian.write(note_id, note_content, tags=["lead", "prospekt"])
            except Exception as e:
                logger.debug(f"Obsidian write feil: {e}")

        if score >= min_score:
            stats["qualified"] += 1
            email = draft_email(company, score)
            qualified_leads.append({
                "company": company_name,
                "city": city,
                "employees": employees,
                "score": score,
                "email": email,
                "org_number": org,
            })

    qualified_leads.sort(key=lambda x: x["score"], reverse=True)
    stats["top_leads"] = qualified_leads[:10]

    # Kø e-poster for topp leads
    if not dry_run:
        for lead in qualified_leads[:15]:
            try:
                _queue_email(lead["email"])
                stats["emails_queued"] += 1
            except Exception as e:
                logger.warning(f"Email queue feil ({lead['company']}): {e}")

    elapsed = int((time.time() - start) * 1000)
    stats["duration_ms"] = elapsed
    stats["run_at"] = datetime.now().isoformat()

    # Logg til brain som daglig aktivitet
    if brain:
        try:
            summary_text = (
                f"Lead pipeline {datetime.now().isoformat()[:10]}: "
                f"{stats['found']} funnet, {stats['new']} nye, "
                f"{stats['qualified']} kvalifiserte (score≥{min_score}), "
                f"{stats['emails_queued']} e-poster kødd."
            )
            brain.remember(summary_text, category="task", tags=["pipeline", "leads"])

            # Daglig notat
            if brain.obsidian:
                brain.obsidian.daily_note(
                    f"\n## Lead Pipeline {datetime.now().strftime('%H:%M')}\n"
                    f"- Funnet: {stats['found']} bedrifter\n"
                    f"- Nye: {stats['new']}\n"
                    f"- Kvalifiserte (≥{min_score}): {stats['qualified']}\n"
                    f"- E-poster: {stats['emails_queued']}\n"
                    f"- Tid: {elapsed}ms\n"
                )
        except Exception:
            pass

    logger.info(
        f"Pipeline ferdig: {stats['found']} funnet, {stats['new']} nye, "
        f"{stats['qualified']} kvalifiserte, {stats['emails_queued']} e-poster — {elapsed}ms"
    )

    return stats


def _queue_email(email: dict):
    """Kø e-post via Instantly.ai eller Brevo."""
    try:
        from tools.email_sender import queue_outreach
        queue_outreach(
            to_name=email["to_company"],
            subject=email["subject"],
            body=email["body"],
            tags=["pipeline", f"score_{email['score']}"],
        )
        return
    except Exception:
        pass

    try:
        from tools.brevo import send_email as brevo_send
        brevo_send(
            to_name=email["to_company"],
            subject=email["subject"],
            body=email["body"],
        )
        return
    except Exception:
        pass

    logger.warning(f"Ingen e-post-sending tilgjengelig for: {email['to_company']}")


def format_report(stats: dict) -> str:
    """Formater pipeline-resultat for Telegram."""
    top = stats.get("top_leads", [])
    lines = [
        f"Lead Pipeline {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        "",
        f"Funnet:        {stats.get('found', 0)} bedrifter",
        f"Nye i KG:      {stats.get('new', 0)}",
        f"Kvalifiserte:  {stats.get('qualified', 0)} (score≥6)",
        f"E-poster:      {stats.get('emails_queued', 0)} kødd",
        f"Tid:           {stats.get('duration_ms', 0)}ms",
    ]

    if stats.get("errors"):
        lines.append(f"\nAdvarsler: {len(stats['errors'])}")

    if top:
        lines.append("\nTopp leads:")
        for i, lead in enumerate(top[:5], 1):
            lines.append(
                f"  {i}. {lead['company']} ({lead['city']}, "
                f"{lead['employees']} ans.) score={lead['score']}"
            )

    return "\n".join(lines)


# ── CLI-kjøring ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    parser = argparse.ArgumentParser(description="NEXUS Lead Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Ikke send e-poster")
    parser.add_argument("--city", help="Kjør kun for én by")
    parser.add_argument("--nace", help="NACE-kode")
    parser.add_argument("--min-score", type=int, default=6)
    args = parser.parse_args()

    cities = [args.city] if args.city else None
    nace_codes = [args.nace] if args.nace else None

    print("Kjører lead pipeline...")
    stats = run_lead_pipeline(
        cities=cities,
        nace_codes=nace_codes,
        min_score=args.min_score,
        dry_run=args.dry_run,
    )
    print(format_report(stats))
