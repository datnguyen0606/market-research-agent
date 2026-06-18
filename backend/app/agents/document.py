import logging
from app.agents.state import ResearchState
from app.rag.embedder import embed_chunks, embed_sparse, rerank
from app.rag.retriever import search_chunks, fetch_parent

logger = logging.getLogger(__name__)


def document_rag_node(state: ResearchState) -> dict:
    messages = state.get("messages") or []
    query = state["query"] if not messages else (messages[-1].content if messages else state["query"])

    logger.info("Document RAG: hybrid search query=%r", query[:80])

    try:
        dense_vecs = embed_chunks([query])
        sparse_vecs = embed_sparse([query])
        query_dense = dense_vecs[0]
        query_sparse = sparse_vecs[0]
    except Exception as exc:
        logger.warning("Document RAG: embedding failed — %s", exc, exc_info=True)
        return {"retrieved_docs": []}

    candidates = search_chunks(query_dense, query_sparse, top_k=20)
    if not candidates:
        logger.info("Document RAG: no chunks found")
        return {"retrieved_docs": []}

    # Rerank candidate snippets for precision
    snippets = [c["text_snippet"] for c in candidates]
    try:
        reranked = rerank(query, snippets, top_n=8)
        top_candidates = [candidates[item["index"]] for item in reranked]
    except Exception as exc:
        logger.warning("Document RAG: reranking failed — %s", exc)
        top_candidates = candidates[:8]

    # Fetch full parent blocks for the top candidates
    parent_texts: list[str] = []
    seen: set[str] = set()
    for c in top_candidates:
        pid = c["parent_id"]
        if pid in seen:
            continue
        seen.add(pid)
        parent = fetch_parent(pid)
        if parent:
            filename = c.get("filename") or parent.get("filename") or "document"
            parent_texts.append(f"Source: {filename}\n\n{parent['full_text']}")

    logger.info("Document RAG: retrieved %d parent blocks", len(parent_texts))
    return {"retrieved_docs": parent_texts}
