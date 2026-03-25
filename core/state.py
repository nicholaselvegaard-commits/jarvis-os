from typing import TypedDict, Annotated, List, Optional, Dict, Any
from langgraph.graph.message import add_messages


class NexusState(TypedDict):
    # Conversation history (auto-merged by LangGraph)
    messages: Annotated[list, add_messages]

    # Current task being processed
    task: str
    task_type: str  # "morning_routine" | "research" | "sales" | "mcp" | "report" | "idle"

    # Lead pipeline
    leads: List[Dict[str, Any]]          # Leads fetched from Apollo.io
    leads_processed: int                  # How many leads we've processed today

    # Email tracking
    emails_sent: List[Dict[str, Any]]    # {to, subject, sent_at, lead_id}
    emails_today: int

    # MCP board
    mcp_inbox: List[Dict[str, Any]]      # Unread messages from Jordan/Manus
    mcp_sent: List[Dict[str, Any]]       # Messages we've posted

    # Daily stats (reset each morning)
    daily_stats: Dict[str, Any]

    # Routing
    next: str                             # Which node to go to next

    # Errors and reflection
    errors: List[str]
    last_reflection: Optional[str]

    # Final output for this cycle
    result: Optional[str]
