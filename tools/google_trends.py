"""
Google Trends tool — trending topics, keyword interest, related queries.
Uses pytrends (no API key needed, scrapes trends.google.com).
"""
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


def _build_pytrends():
    from pytrends.request import TrendReq
    return TrendReq(hl="en-US", tz=60, timeout=(10, 25), retries=2, backoff_factor=0.5)


def get_interest_over_time(
    keywords: list[str],
    timeframe: str = "today 3-m",
    geo: str = "",
) -> dict:
    """
    Get interest over time for up to 5 keywords.

    Args:
        keywords: List of up to 5 keywords
        timeframe: e.g. 'today 3-m', 'today 12-m', 'now 7-d', 'now 1-d'
        geo: Country code e.g. 'NO', 'US', '' for worldwide

    Returns:
        Dict with keyword → list of (date, value) tuples
    """
    try:
        pt = _build_pytrends()
        pt.build_payload(keywords[:5], timeframe=timeframe, geo=geo)
        df = pt.interest_over_time()
        if df is None or df.empty:
            return {"error": "No data returned"}
        result = {}
        for kw in keywords[:5]:
            if kw in df.columns:
                series = df[kw].dropna()
                # Return last 10 data points
                recent = [(str(idx.date()), int(val)) for idx, val in series.tail(10).items()]
                result[kw] = recent
        return result
    except Exception as e:
        logger.error(f"google_trends get_interest_over_time error: {e}")
        return {"error": str(e)}


def get_trending_searches(geo: str = "norway") -> list[str]:
    """
    Get today's trending searches.

    Args:
        geo: Country name e.g. 'norway', 'united_states', 'united_kingdom'

    Returns:
        List of trending search terms
    """
    try:
        pt = _build_pytrends()
        df = pt.trending_searches(pn=geo)
        return df[0].tolist()[:20]
    except Exception as e:
        logger.error(f"google_trends trending_searches error: {e}")
        return [f"Error: {e}"]


def get_related_queries(keyword: str, geo: str = "") -> dict:
    """
    Get related queries for a keyword (top + rising).

    Args:
        keyword: Search keyword
        geo: Country code e.g. 'NO', 'US', '' for worldwide

    Returns:
        Dict with 'top' and 'rising' query lists
    """
    try:
        pt = _build_pytrends()
        pt.build_payload([keyword], timeframe="today 3-m", geo=geo)
        related = pt.related_queries()
        result = {}
        if keyword in related:
            kw_data = related[keyword]
            if kw_data.get("top") is not None and not kw_data["top"].empty:
                result["top"] = kw_data["top"]["query"].head(10).tolist()
            if kw_data.get("rising") is not None and not kw_data["rising"].empty:
                result["rising"] = kw_data["rising"]["query"].head(10).tolist()
        return result
    except Exception as e:
        logger.error(f"google_trends related_queries error: {e}")
        return {"error": str(e)}


def get_keyword_suggestions(keyword: str) -> list[str]:
    """Get keyword suggestions from Google Trends."""
    try:
        pt = _build_pytrends()
        suggestions = pt.suggestions(keyword=keyword)
        return [s["title"] for s in suggestions[:10]]
    except Exception as e:
        logger.error(f"google_trends suggestions error: {e}")
        return [f"Error: {e}"]
