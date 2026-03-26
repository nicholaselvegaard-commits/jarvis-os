"""
Statistics Norway (SSB) — gratis API for norsk markedsdata.
Ingen API-key. Data under NLOD-lisens.

Tabeller:
  07459 — Befolkning etter region, kjønn, alder, år
  04861 — Bedrifter etter næring
  12203 — Omsetning etter næring
"""
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)
BASE = "https://data.ssb.no/api/v0/no/table"


def get_population(region_code: str = "0", year: str = "2024") -> dict:
    """
    Hent folkemengde for en region.
    region_code: '0'=hele landet, '1804'=Bodø, '0301'=Oslo, '4601'=Bergen
    """
    # Sum all ages for one gender to get total population per region
    query = {
        "query": [
            {"code": "Region", "selection": {"filter": "item", "values": [region_code]}},
            {"code": "Kjonn", "selection": {"filter": "item", "values": ["1"]}},
            {"code": "ContentsCode", "selection": {"filter": "item", "values": ["Personer1"]}},
            {"code": "Tid", "selection": {"filter": "item", "values": [year]}},
        ],
        "response": {"format": "json-stat2"},
    }
    try:
        resp = httpx.post(f"{BASE}/07459", json=query, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        values = [v for v in data.get("value", []) if v is not None]
        pop_men = sum(values)
        return {"region": region_code, "population": pop_men * 2, "year": year, "note": "estimert fra menn*2"}
    except Exception as e:
        logger.error(f"SSB population error: {e}")
        return {"region": region_code, "population": None, "error": str(e)}


def search_companies_ssb(industry_code: Optional[str] = None) -> list[dict]:
    """
    Hent bedrifter per næring fra SSB (tabell 04861).
    """
    values = [industry_code] if industry_code else []
    filter_type = "item" if industry_code else "all"
    query = {
        "query": [
            {"code": "NACE2007", "selection": {"filter": filter_type, "values": values or ["*"]}},
            {"code": "Tid", "selection": {"filter": "top", "values": ["1"]}},
        ],
        "response": {"format": "json-stat2"},
    }
    try:
        resp = httpx.post(f"{BASE}/04861", json=query, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        dims = data.get("dimension", {})
        nace_dim = dims.get("NACE2007", {}).get("category", {})
        labels = nace_dim.get("label", {})
        values_data = data.get("value", [])
        ids = list(labels.keys())
        return [
            {"code": ids[i], "industry": labels[ids[i]], "company_count": values_data[i]}
            for i in range(min(len(ids), len(values_data)))
            if values_data[i]
        ]
    except Exception as e:
        logger.error(f"SSB companies error: {e}")
        return []


def market_summary(municipality_code: str = "1804") -> str:
    """
    Generer markedsoppsummering for en norsk kommune.
    Bodø=1804, Oslo=0301, Bergen=4601, Trondheim=5001
    """
    pop_data = get_population(region_code=municipality_code)
    pop = pop_data.get("population", "ukjent")

    municipality_names = {
        "1804": "Bodø", "0301": "Oslo", "4601": "Bergen",
        "5001": "Trondheim", "1103": "Stavanger",
    }
    name = municipality_names.get(municipality_code, f"Kommune {municipality_code}")

    return (
        f"Marked: {name} (kode {municipality_code})\n"
        f"Befolkning: {pop:,} innbyggere\n"
        f"Kilde: SSB (gratis, oppdatert)\n"
        f"Tips: For lead gen, bruk brreg.find_leads(municipality='{name.upper()}')"
    )
