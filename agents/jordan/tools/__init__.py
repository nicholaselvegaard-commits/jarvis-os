"""Sub-agent registry. Jarvis delegates to these via tools/delegate.py."""

def _lazy(module: str, cls: str):
    """Lazy import to avoid circular/startup errors."""
    import importlib
    m = importlib.import_module(module)
    return getattr(m, cls)

REGISTRY: dict[str, str] = {
    "sales":     "agents.jordan.tools.sales_agent:SalesAgent",
    "research":  "agents.jordan.tools.research_agent:ResearchAgent",
    "finance":   "agents.jordan.tools.finance_agent:FinanceAgent",
    "content":   "agents.jordan.tools.content_agent:ContentAgent",
    "dev":       "agents.jordan.tools.dev_agent:DevAgent",
    "scout":     "agents.jordan.tools.scout_agent:ScoutAgent",
    "email":     "agents.jordan.tools.email_agent:EmailAgent",
}

def get_agent(name: str):
    """Get agent class by name. Lazy-loaded."""
    if name not in REGISTRY:
        raise KeyError(f"Unknown agent: {name}. Available: {list(REGISTRY)}")
    module, cls = REGISTRY[name].split(":")
    return _lazy(module, cls)

__all__ = ["REGISTRY", "get_agent"]
