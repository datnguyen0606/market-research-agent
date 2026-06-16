import logging
from langgraph.graph import StateGraph, END

from app.agents.state import AgentReportState
from app.agents.router import router_node
from app.agents.document import document_rag_node
from app.agents.search import market_search_node
from app.agents.analyst import analyst_node
from app.agents.critic import critic_node

logger = logging.getLogger(__name__)


def _after_router(state: AgentReportState):
    """Fan-out to RAG+search for initial generation; skip to analyst for chat follow-ups."""
    if state.get("messages"):
        return "analyst"
    return ["document_rag", "market_search"]


def _critic_edge(state: AgentReportState) -> str:
    if state["is_approved"] or state.get("iterations", 0) >= 3:
        return END
    return "analyst"


def build_graph(checkpointer=None):
    graph = StateGraph(AgentReportState)

    graph.add_node("router", router_node)
    graph.add_node("document_rag", document_rag_node)
    graph.add_node("market_search", market_search_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("critic", critic_node)

    graph.set_entry_point("router")
    graph.add_conditional_edges("router", _after_router)
    graph.add_edge("document_rag", "analyst")
    graph.add_edge("market_search", "analyst")
    graph.add_edge("analyst", "critic")
    graph.add_conditional_edges("critic", _critic_edge)

    return graph.compile(checkpointer=checkpointer)
