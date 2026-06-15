import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import StateGraph, END

from app.agents.state import AgentReportState
from app.agents.router import router_node
from app.agents.document import document_rag_node
from app.agents.search import market_search_node
from app.agents.analyst import analyst_node
from app.agents.critic import critic_node

logger = logging.getLogger(__name__)

# In-memory stores (demo — resets on restart)
task_store: dict[str, dict[str, Any]] = {}
active_jobs: dict[str, str] = {}  # ticker -> task_id for in-progress jobs


def _critic_edge(state: AgentReportState) -> str:
    if state["is_approved"] or state.get("iterations", 0) >= 3:
        return END
    return "analyst"


def build_graph():
    graph = StateGraph(AgentReportState)

    graph.add_node("router", router_node)
    graph.add_node("document_rag", document_rag_node)
    graph.add_node("market_search", market_search_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("critic", critic_node)

    graph.set_entry_point("router")
    graph.add_edge("router", "document_rag")
    graph.add_edge("router", "market_search")
    graph.add_edge("document_rag", "analyst")
    graph.add_edge("market_search", "analyst")
    graph.add_edge("analyst", "critic")
    graph.add_conditional_edges("critic", _critic_edge)

    return graph.compile()


async def run_graph(task_id: str, payload) -> None:
    ticker = payload.ticker
    try:
        graph = build_graph()
        initial_state: AgentReportState = {
            "company_name": payload.company_name,
            "ticker": ticker,
            "raw_query": f"Financial analysis of {payload.company_name} ({ticker})",
            "focus_areas": payload.focus_areas,
            "retrieved_financials": [],
            "market_news": [],
            "financial_analysis": {},
            "critic_feedback": None,
            "iterations": 0,
            "is_approved": False,
            "final_report_json": None,
        }

        task_store[task_id]["current_node"] = "router"
        result = await graph.ainvoke(initial_state)

        validation_passed = result.get("is_approved", False)
        report = result.get("final_report_json") or {}

        task_store[task_id] = {
            "status": "completed",
            "company_name": payload.company_name,
            "ticker": ticker,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "validation_passed": validation_passed,
            "validation_warning": (
                "Report delivered after 3 validation attempts without full approval. "
                "Financial figures should be independently verified."
            ) if not validation_passed else None,
            "report_data": report,
            "current_node": None,
        }

    except ValueError as exc:
        task_store[task_id] = {
            "status": "failed",
            "error_message": str(exc),
            "current_node": None,
        }
    except Exception:
        logger.exception("Unexpected error in run_graph for task %s", task_id)
        task_store[task_id] = {
            "status": "failed",
            "error_message": "An unexpected error occurred. Please try again.",
            "current_node": None,
        }
    finally:
        active_jobs.pop(ticker, None)
