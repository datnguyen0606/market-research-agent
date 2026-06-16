import logging
from app.agents.state import AgentReportState
from app.rag.retriever import ticker_has_index

logger = logging.getLogger(__name__)


def router_node(state: AgentReportState) -> dict:
    messages = state.get("messages") or []

    if messages:
        # Chat follow-up — reset control-flow fields so Analyst+Critic run fresh
        logger.info("Router: chat mode for ticker=%s", state["ticker"])
        return {
            "iterations": 0,
            "is_approved": False,
            "critic_feedback": None,
            "final_report_json": None,
        }

    # Initial generation
    has_index = ticker_has_index(state["ticker"])
    logger.info("Router: initial mode ticker=%s has_index=%s", state["ticker"], has_index)
    return {}
