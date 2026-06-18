import logging
from langgraph.graph import StateGraph, END

from app.agents.state import ResearchState
from app.agents.router import router_node
from app.agents.document import document_rag_node
from app.agents.search import web_search_node
from app.agents.analyst import analyst_node
from app.agents.grounding import grounding_node

logger = logging.getLogger(__name__)


def _after_router(state: ResearchState):
    """Fan out to both retrieval sources for new queries; skip to analyst for chat follow-ups."""
    if state.get("messages"):
        return "analyst"
    return ["document_rag", "web_search"]


def build_graph(checkpointer=None):
    graph = StateGraph(ResearchState)

    graph.add_node("router", router_node)
    graph.add_node("document_rag", document_rag_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("grounding", grounding_node)

    graph.set_entry_point("router")
    graph.add_conditional_edges("router", _after_router)
    graph.add_edge("document_rag", "analyst")
    graph.add_edge("web_search", "analyst")
    graph.add_edge("analyst", "grounding")
    graph.add_edge("grounding", END)

    return graph.compile(checkpointer=checkpointer)
