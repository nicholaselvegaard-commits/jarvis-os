"""
Market data via Yahoo Finance (yfinance). No API key required.
For real-time professional data, set ALPHAVANTAGE_API_KEY.
"""
import logging
from dataclasses import dataclass
from datetime import datetime

from tools.retry import with_retry

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False


@dataclass
class Quote:
    ticker: str
    price: float
    change_pct: float
    volume: int
    market_cap: float
    pe_ratio: float
    week_52_high: float
    week_52_low: float


@with_retry()
def get_quote(ticker: str) -> Quote:
    """
    Get current stock/crypto quote.

    Args:
        ticker: Yahoo Finance ticker (e.g. 'AAPL', 'BTC-USD', 'EQNR.OL')

    Returns:
        Quote dataclass
    """
    if not _YF_AVAILABLE:
        raise ImportError("Install yfinance: pip install yfinance")

    info = yf.Ticker(ticker).info
    hist = yf.Ticker(ticker).history(period="2d")

    if hist.empty:
        raise RuntimeError(f"No data returned for ticker {ticker}")

    current = float(hist["Close"].iloc[-1])
    prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
    change_pct = ((current - prev) / prev * 100) if prev else 0

    return Quote(
        ticker=ticker,
        price=current,
        change_pct=round(change_pct, 2),
        volume=int(hist["Volume"].iloc[-1]),
        market_cap=info.get("marketCap", 0),
        pe_ratio=info.get("trailingPE", 0) or 0,
        week_52_high=info.get("fiftyTwoWeekHigh", 0) or 0,
        week_52_low=info.get("fiftyTwoWeekLow", 0) or 0,
    )


@with_retry()
def get_history(ticker: str, period: str = "1mo", interval: str = "1d") -> list[dict]:
    """
    Get historical OHLCV data.

    Args:
        ticker: Yahoo Finance ticker
        period: e.g. '1d', '5d', '1mo', '3mo', '1y'
        interval: e.g. '1m', '5m', '1h', '1d'

    Returns:
        List of dicts with date, open, high, low, close, volume
    """
    if not _YF_AVAILABLE:
        raise ImportError("Install yfinance: pip install yfinance")

    hist = yf.Ticker(ticker).history(period=period, interval=interval)
    result = []
    for idx, row in hist.iterrows():
        result.append({
            "date": str(idx.date()),
            "open": round(float(row["Open"]), 4),
            "high": round(float(row["High"]), 4),
            "low": round(float(row["Low"]), 4),
            "close": round(float(row["Close"]), 4),
            "volume": int(row["Volume"]),
        })
    return result


def format_quote(q: Quote) -> str:
    """Format a quote for Telegram display."""
    direction = "▲" if q.change_pct >= 0 else "▼"
    return (
        f"*{q.ticker}*: ${q.price:,.2f} {direction} {abs(q.change_pct):.2f}%\n"
        f"52w: ${q.week_52_low:,.0f} — ${q.week_52_high:,.0f}"
    )
