from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from core.state import NexusState
from agents.orchestrator import orchestrator_node
from agents.research_agent import research_node
from agents.sales_agent import sales_node
from agents.mcp_agent import mcp_node
from agents.reporter import reporter_node
import sqlite3


def route(state: NexusState) -> str:
    """Route from orchestrator to the appropriate sub-agent."""
    return state.get("next", END)


def build_graph(db_path: str = "nexus.db"):
    # Persistent memory via SQLite checkpointing
    conn = sqlite3.connect(db_path, check_same_thread=False)
    memory = SqliteSaver(conn)

    workflow = StateGraph(NexusState)

    # Register all nodes
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("research", research_node)
    workflow.add_node("sales", sales_node)
    workflow.add_node("mcp", mcp_node)
    workflow.add_node("reporter", reporter_node)

    # Entry point
    workflow.set_entry_point("orchestrator")

    # Conditional routing from orchestrator
    workflow.add_conditional_edges(
        "orchestrator",
        route,
        {
            "research": "research",
            "sales": "sales",
            "mcp": "mcp",
            "reporter": "reporter",
            END: END,
        },
    )

    # All sub-agents return to orchestrator for next decision
    workflow.add_edge("research", "orchestrator")
    workflow.add_edge("sales", "orchestrator")
    workflow.add_edge("mcp", "orchestrator")
    workflow.add_edge("reporter", END)

    return workflow.compile(checkpointer=memory)
