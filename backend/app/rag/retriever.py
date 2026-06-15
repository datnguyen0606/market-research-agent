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

COLLECTION_CHUNKS = "financial_chunks"
COLLECTION_PARENTS = "parent_blocks"
VECTOR_SIZE = 768


def _client() -> QdrantClient:
    return QdrantClient(
        url=os.getenv("QDRANT_URL"),
        api_key=os.getenv("QDRANT_API_KEY"),
    )


def _ensure_collections(client: QdrantClient) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_CHUNKS not in existing:
        client.create_collection(
            COLLECTION_CHUNKS,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
    if COLLECTION_PARENTS not in existing:
        # Payload-only collection — use a tiny dummy vector dimension
        client.create_collection(
            COLLECTION_PARENTS,
            vectors_config=VectorParams(size=1, distance=Distance.COSINE),
        )


def ticker_has_index(ticker: str) -> bool:
    client = _client()
    _ensure_collections(client)
    result = client.count(
        COLLECTION_CHUNKS,
        count_filter=Filter(must=[FieldCondition(key="ticker", match=MatchValue(value=ticker))]),
        exact=True,
    )
    return result.count > 0


def delete_ticker_index(ticker: str) -> None:
    client = _client()
    _ensure_collections(client)
    client.delete(
        COLLECTION_CHUNKS,
        points_selector=Filter(must=[FieldCondition(key="ticker", match=MatchValue(value=ticker))]),
    )
    client.delete(
        COLLECTION_PARENTS,
        points_selector=Filter(must=[FieldCondition(key="ticker", match=MatchValue(value=ticker))]),
    )


def upsert_to_qdrant(
    ticker: str, chunks: list[dict], embeddings: list[list[float]], r2_key: str
) -> None:
    client = _client()
    _ensure_collections(client)

    child_points = []
    parent_points = []

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
        elif chunk["type"] == "parent":
            parent_points.append(
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk["id"])),
                    vector=[0.0],  # dummy vector for payload-only collection
                    payload={
                        "ticker": ticker,
                        "full_text": chunk["text"],
                        "page": chunk["page"],
                        "r2_key": r2_key,
                        "parent_id": chunk["id"],
                    },
                )
            )

    if child_points:
        client.upsert(COLLECTION_CHUNKS, points=child_points)
    if parent_points:
        client.upsert(COLLECTION_PARENTS, points=parent_points)


def search_chunks(ticker: str, query_vector: list[float], top_k: int = 20) -> list[dict]:
    client = _client()
    results = client.search(
        COLLECTION_CHUNKS,
        query_vector=query_vector,
        query_filter=Filter(must=[FieldCondition(key="ticker", match=MatchValue(value=ticker))]),
        limit=top_k,
        with_payload=True,
    )
    return [{"text_snippet": r.payload["text_snippet"], "parent_id": r.payload["parent_id"], "score": r.score} for r in results]


def fetch_parent(parent_id: str, ticker: str) -> dict | None:
    client = _client()
    results = client.scroll(
        COLLECTION_PARENTS,
        scroll_filter=Filter(must=[
            FieldCondition(key="parent_id", match=MatchValue(value=parent_id)),
            FieldCondition(key="ticker", match=MatchValue(value=ticker)),
        ]),
        limit=1,
        with_payload=True,
    )
    points = results[0]
    if points:
        return points[0].payload
    return None
