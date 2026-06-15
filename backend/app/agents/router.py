import logging
from app.agents.state import AgentReportState
from app.rag.retriever import ticker_has_index

logger = logging.getLogger(__name__)


def router_node(state: AgentReportState) -> dict:
    ticker = state["ticker"]
    has_index = ticker_has_index(ticker)
    logger.info("Router: ticker=%s has_index=%s", ticker, has_index)
    # State is passed through; document_rag will re-check ticker_has_index
    return {}
