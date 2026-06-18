import asyncio
import logging

from app.agents.state import ResearchState
from app.agents.document import document_rag_node
from app.agents.search import web_search_node

logger = logging.getLogger(__name__)


async def retrieval_node(state: ResearchState) -> dict:
    """
    Run document RAG and web search in true parallel via asyncio.gather.

    Using asyncio.gather here instead of LangGraph's conditional fan-out
    avoids version-specific behaviour where one sync node completing before
    the other is scheduled can cause the second node to be silently skipped.
    """
    if state.get("messages"):
        # Chat follow-up — router already decided to skip retrieval
        return {}

    logger.info("Retrieval: starting document_rag + web_search in parallel")

    doc_task = asyncio.to_thread(document_rag_node, state)
    web_task = asyncio.to_thread(web_search_node, state)

    doc_result, web_result = await asyncio.gather(doc_task, web_task)

    logger.info(
        "Retrieval: done — docs=%d web=%d",
        len(doc_result.get("retrieved_docs", [])),
        len(web_result.get("web_results", [])),
    )

    return {
        "retrieved_docs": doc_result.get("retrieved_docs", []),
        "web_results": web_result.get("web_results", []),
    }
