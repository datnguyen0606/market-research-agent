import logging
import os
from tavily import TavilyClient
from app.agents.state import AgentReportState
from app.rag.embedder import rerank

logger = logging.getLogger(__name__)


def market_search_node(state: AgentReportState) -> dict:
    ticker = state["ticker"]
    company_name = state["company_name"]
    query = f"{company_name} {ticker} financial news earnings analyst"

    logger.info("Market Search: querying Tavily for ticker=%s", ticker)
    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

    try:
        response = client.search(query, max_results=20, search_depth="advanced")
        results = response.get("results", [])
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        return {"market_news": []}

    if not results:
        return {"market_news": []}

    snippets = [r.get("content", "") for r in results if r.get("content")]
    if not snippets:
        return {"market_news": []}

    try:
        reranked = rerank(query, snippets, top_n=5)
        top_snippets = [snippets[item["index"]] for item in reranked]
    except Exception as exc:
        logger.warning("Reranking failed, using raw top-5: %s", exc)
        top_snippets = snippets[:5]

    logger.info("Market Search: selected %d news snippets", len(top_snippets))
    return {"market_news": top_snippets}
