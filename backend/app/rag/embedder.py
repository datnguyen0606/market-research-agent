import os
import requests
from fastembed import SparseTextEmbedding

JINA_API_KEY = os.getenv("JINA_API_KEY")
EMBED_MODEL = "jina-embeddings-v2-base-en"
RERANK_MODEL = "jina-reranker-v2-base-multilingual"
JINA_HEADERS = {"Content-Type": "application/json"}

# Qdrant/bm25 is a lightweight statistical model (no neural net, ~2 MB download).
SPARSE_MODEL_NAME = "Qdrant/bm25"
_sparse_model: SparseTextEmbedding | None = None


def _auth_headers() -> dict:
    return {**JINA_HEADERS, "Authorization": f"Bearer {JINA_API_KEY}"}


def _get_sparse_model() -> SparseTextEmbedding:
    global _sparse_model
    if _sparse_model is None:
        _sparse_model = SparseTextEmbedding(model_name=SPARSE_MODEL_NAME)
    return _sparse_model


def embed_chunks(texts: list[str]) -> list[list[float]]:
    response = requests.post(
        "https://api.jina.ai/v1/embeddings",
        headers=_auth_headers(),
        json={"input": texts, "model": EMBED_MODEL},
        timeout=60,
    )
    response.raise_for_status()
    return [item["embedding"] for item in response.json()["data"]]


def embed_sparse(texts: list[str]) -> list[dict]:
    """Return BM25 sparse vectors as {indices: list[int], values: list[float]}."""
    model = _get_sparse_model()
    results = []
    for emb in model.embed(texts):
        results.append({"indices": emb.indices.tolist(), "values": emb.values.tolist()})
    return results


def rerank(query: str, documents: list[str], top_n: int = 5) -> list[dict]:
    response = requests.post(
        "https://api.jina.ai/v1/rerank",
        headers=_auth_headers(),
        json={"model": RERANK_MODEL, "query": query, "documents": documents, "top_n": top_n},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["results"]
