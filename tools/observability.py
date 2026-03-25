"""
Structured logging and optional Langfuse tracing.
Import setup_logging() in run.py to configure the log system.
"""
import logging
import os
import sys
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with console + file handlers."""
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "agent.log", encoding="utf-8"),
    ]

    # Errors also go to a separate errors file
    err_handler = logging.FileHandler(LOG_DIR / "agent_errors.log", encoding="utf-8")
    err_handler.setLevel(logging.ERROR)
    handlers.append(err_handler)

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
    )

    # Quiet noisy libraries
    for lib in ("httpx", "httpcore", "telegram", "apscheduler"):
        logging.getLogger(lib).setLevel(logging.WARNING)


try:
    from langfuse import Langfuse
    _langfuse = Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
        host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
    ) if os.getenv("LANGFUSE_PUBLIC_KEY") else None
    _LANGFUSE_AVAILABLE = _langfuse is not None
except ImportError:
    _langfuse = None
    _LANGFUSE_AVAILABLE = False


def trace(name: str, input_data: dict, output_data: dict, model: str = "", cost_usd: float = 0.0) -> None:
    """
    Record a trace in Langfuse (no-op if not configured).

    Args:
        name: Operation name (e.g. "agent_run", "tool_call")
        input_data: Input dict
        output_data: Output dict
        model: Model used (optional)
        cost_usd: Cost in USD (optional)
    """
    if not _LANGFUSE_AVAILABLE or not _langfuse:
        return
    try:
        t = _langfuse.trace(name=name, input=input_data, output=output_data)
        if model:
            t.generation(
                name=name,
                model=model,
                input=input_data,
                output=output_data,
                usage={"total_cost": cost_usd} if cost_usd else None,
            )
    except Exception as exc:
        logging.getLogger(__name__).warning(f"Langfuse trace failed: {exc}")
