import os
import requests

JINA_API_KEY = os.getenv("JINA_API_KEY")
EMBED_MODEL = "jina-embeddings-v2-base-en"
RERANK_MODEL = "jina-reranker-v2-base-multilingual"
JINA_HEADERS = {"Content-Type": "application/json"}


def _auth_headers() -> dict:
    return {**JINA_HEADERS, "Authorization": f"Bearer {JINA_API_KEY}"}


def embed_chunks(texts: list[str]) -> list[list[float]]:
    response = requests.post(
        "https://api.jina.ai/v1/embeddings",
        headers=_auth_headers(),
        json={"input": texts, "model": EMBED_MODEL},
        timeout=60,
    )
    response.raise_for_status()
    return [item["embedding"] for item in response.json()["data"]]


def rerank(query: str, documents: list[str], top_n: int = 5) -> list[dict]:
    response = requests.post(
        "https://api.jina.ai/v1/rerank",
        headers=_auth_headers(),
        json={"model": RERANK_MODEL, "query": query, "documents": documents, "top_n": top_n},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["results"]
