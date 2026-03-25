"""
Research Tool — Perplexity API for sanntids web-research.
"""

import os
import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"


def search(query: str, focus: str = "internet") -> str:
    """Søk via Perplexity API. focus: 'internet' | 'news' | 'scholar'"""
    if not PERPLEXITY_API_KEY:
        logger.error("PERPLEXITY_API_KEY mangler")
        return "Feil: PERPLEXITY_API_KEY ikke satt."

    model = "sonar-pro" if focus == "scholar" else "sonar"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Du er en research-assistent for NEXUS. "
                    "Gi presise, faktabaserte svar. "
                    "Fokuser på forretningsrelevant informasjon."
                ),
            },
            {"role": "user", "content": query},
        ],
        "max_tokens": 1024,
        "return_citations": True,
    }

    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(PERPLEXITY_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            return "Ingen resultater fra Perplexity."
        content = choices[0].get("message", {}).get("content", "")
        logger.info(f"Perplexity: '{query[:60]}' — {len(content)} tegn")
        return content
    except requests.exceptions.RequestException as e:
        logger.error(f"Perplexity feil: {e}")
        return f"Søkefeil: {e}"


def research_company(company_name: str, country: str = "Norway") -> str:
    return search(
        f"Tell me about {company_name} in {country}: what they do, size, "
        f"key decision makers, recent news, and AI automation pain points."
    )


def find_opportunities(sector: str) -> str:
    return search(
        f"Current tenders, opportunities and AI adoption in the {sector} "
        f"sector in Norway 2026. Focus on contracts and decision makers.",
        focus="news",
    )


def research_lead(first_name: str, last_name: str, company: str) -> str:
    return search(
        f"Information about {first_name} {last_name} at {company}: "
        f"role, recent activity, company challenges, news last 3 months."
    )
