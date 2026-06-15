import logging
from app.agents.state import AgentReportState
from app.rag.embedder import embed_chunks, rerank
from app.rag.retriever import ticker_has_index, search_chunks, fetch_parent

logger = logging.getLogger(__name__)


def document_rag_node(state: AgentReportState) -> dict:
    ticker = state["ticker"]
    query = state["raw_query"]

    if not ticker_has_index(ticker):
        logger.info("Document RAG: no index for ticker=%s, skipping", ticker)
        return {"retrieved_financials": []}

    logger.info("Document RAG: retrieving context for ticker=%s", ticker)
    query_vector = embed_chunks([query])[0]
    candidates = search_chunks(ticker, query_vector, top_k=20)

    if not candidates:
        return {"retrieved_financials": []}

    candidate_texts = [c["text_snippet"] for c in candidates]
    reranked = rerank(query, candidate_texts, top_n=5)
    top_parent_ids = []
    for item in reranked:
        idx = item["index"]
        top_parent_ids.append(candidates[idx]["parent_id"])

    parent_texts = []
    seen = set()
    for parent_id in top_parent_ids:
        if parent_id in seen:
            continue
        seen.add(parent_id)
        parent = fetch_parent(parent_id, ticker)
        if parent:
            parent_texts.append(parent["full_text"])

    logger.info("Document RAG: retrieved %d parent blocks", len(parent_texts))
    return {"retrieved_financials": parent_texts}
