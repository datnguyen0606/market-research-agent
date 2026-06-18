import logging
from langgraph.graph import StateGraph, END

from app.agents.state import ResearchState
from app.agents.router import router_node
from app.agents.retrieval import retrieval_node
from app.agents.analyst import analyst_node
from app.agents.grounding import grounding_node

logger = logging.getLogger(__name__)


def _after_router(state: ResearchState) -> str:
    """Chat follow-ups skip retrieval and go straight to analyst."""
    if state.get("messages"):
        return "analyst"
    return "retrieval"


def build_graph(checkpointer=None):
    graph = StateGraph(ResearchState)

    graph.add_node("router", router_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("grounding", grounding_node)

    graph.set_entry_point("router")
    graph.add_conditional_edges("router", _after_router)
    graph.add_edge("retrieval", "analyst")
    graph.add_edge("analyst", "grounding")
    graph.add_edge("grounding", END)

    return graph.compile(checkpointer=checkpointer)
