"""
Perplexity AI client — real-time web search with AI reasoning.

Best for: deep research with cited sources, current events, market analysis.
Uses sonar-pro model by default (better quality, supports larger context).

Usage:
    from tools.perplexity_client import search, research
"""
import logging
import os
import httpx

logger = logging.getLogger(__name__)

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
BASE_URL = "https://api.perplexity.ai/chat/completions"


def search(query: str, model: str = "sonar-pro") -> dict:
    """
    Search the web with Perplexity AI. Returns answer + citations.

    Args:
        query: What to search for
        model: sonar-pro (best), sonar (fast), sonar-reasoning (for analysis)

    Returns:
        {"answer": str, "citations": list[str]}
    """
    if not PERPLEXITY_API_KEY:
        raise ValueError("PERPLEXITY_API_KEY not set in .env")

    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Be precise and factual. Include sources."},
            {"role": "user", "content": query},
        ],
        "return_citations": True,
        "return_related_questions": False,
        "search_recency_filter": "month",
    }

    with httpx.Client(timeout=30) as client:
        r = client.post(BASE_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()

    answer = data["choices"][0]["message"]["content"]
    citations = data.get("citations", [])
    logger.info(f"Perplexity search: '{query[:50]}' → {len(citations)} citations")
    return {"answer": answer, "citations": citations}


def research(topic: str, depth: str = "comprehensive") -> str:
    """
    Deep research on a topic. Uses sonar-reasoning for better analysis.
    Returns a formatted research report.
    """
    prompt = f"""Research this topic thoroughly for a business/tech context:
{topic}

Include:
1. Current state of the market/field
2. Key players and their strategies
3. Revenue models and pricing
4. Opportunities and threats
5. Actionable insights"""

    result = search(prompt, model="sonar-reasoning")
    report = result["answer"]
    if result["citations"]:
        report += "\n\nSources:\n" + "\n".join(f"- {c}" for c in result["citations"][:5])
    return report
