import os
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from app.db.postgres import fetch_parent_block

COLLECTION_CHUNKS = "financial_chunks"
VECTOR_SIZE = 768


def _client() -> QdrantClient:
    return QdrantClient(
        url=os.getenv("QDRANT_URL"),
        api_key=os.getenv("QDRANT_API_KEY"),
    )


def _ensure_collection(client: QdrantClient) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_CHUNKS not in existing:
        client.create_collection(
            COLLECTION_CHUNKS,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def ticker_has_index(ticker: str) -> bool:
    client = _client()
    _ensure_collection(client)
    result = client.count(
        COLLECTION_CHUNKS,
        count_filter=Filter(must=[FieldCondition(key="ticker", match=MatchValue(value=ticker))]),
        exact=True,
    )
    return result.count > 0


def delete_ticker_index(ticker: str) -> None:
    """Delete child vectors from Qdrant. Caller is responsible for deleting parent blocks from PostgreSQL."""
    client = _client()
    _ensure_collection(client)
    client.delete(
        COLLECTION_CHUNKS,
        points_selector=Filter(must=[FieldCondition(key="ticker", match=MatchValue(value=ticker))]),
    )


def upsert_to_qdrant(
    ticker: str, chunks: list[dict], embeddings: list[list[float]], r2_key: str
) -> None:
    """Upsert child chunk vectors to Qdrant. Parent blocks are stored in PostgreSQL separately."""
    client = _client()
    _ensure_collection(client)

    child_points = []
    child_vectors = iter(embeddings)

    for chunk in chunks:
        if chunk["type"] == "child":
            vector = next(child_vectors)
            child_points.append(
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk["id"])),
                    vector=vector,
                    payload={
                        "type": "child",
                        "parent_id": chunk["parent_id"],
                        "ticker": ticker,
                        "r2_key": r2_key,
                        "text_snippet": chunk["text"][:500],
                        "page": chunk["page"],
                        "chunk_id": chunk["id"],
                    },
                )
            )

    if child_points:
        client.upsert(COLLECTION_CHUNKS, points=child_points)


def search_chunks(ticker: str, query_vector: list[float], top_k: int = 20) -> list[dict]:
    client = _client()
    results = client.search(
        COLLECTION_CHUNKS,
        query_vector=query_vector,
        query_filter=Filter(must=[FieldCondition(key="ticker", match=MatchValue(value=ticker))]),
        limit=top_k,
        with_payload=True,
    )
    return [
        {"text_snippet": r.payload["text_snippet"], "parent_id": r.payload["parent_id"], "score": r.score}
        for r in results
    ]


def fetch_parent(parent_id: str, ticker: str) -> dict | None:
    """Fetch full parent block text from PostgreSQL."""
    return fetch_parent_block(parent_id, ticker)
