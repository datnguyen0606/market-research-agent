import os
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    SparseVectorParams,
    SparseIndexParams,
    SparseVector,
    PointStruct,
    Prefetch,
    FusionQuery,
    Fusion,
)

from app.db.postgres import fetch_parent_block

COLLECTION_CHUNKS = "financial_chunks"
DENSE_VECTOR_SIZE = 768
DENSE_NAME = "dense"
SPARSE_NAME = "sparse"


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
            vectors_config={
                DENSE_NAME: VectorParams(size=DENSE_VECTOR_SIZE, distance=Distance.COSINE),
            },
            sparse_vectors_config={
                SPARSE_NAME: SparseVectorParams(index=SparseIndexParams(on_disk=False)),
            },
        )


def delete_doc_index(doc_id: str) -> None:
    """Delete all vectors belonging to a specific uploaded document."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    client = _client()
    _ensure_collection(client)
    client.delete(
        COLLECTION_CHUNKS,
        points_selector=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]),
    )


def upsert_to_qdrant(
    doc_id: str,
    chunks: list[dict],
    dense_embeddings: list[list[float]],
    sparse_embeddings: list[dict],
    r2_key: str,
    filename: str = "",
) -> None:
    client = _client()
    _ensure_collection(client)

    child_chunks = [c for c in chunks if c["type"] == "child"]
    if len(child_chunks) != len(dense_embeddings) or len(child_chunks) != len(sparse_embeddings):
        raise ValueError("Mismatch between chunks and embeddings counts")

    points = []
    for chunk, dense_vec, sparse_vec in zip(child_chunks, dense_embeddings, sparse_embeddings):
        points.append(
            PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk["id"])),
                vector={
                    DENSE_NAME: dense_vec,
                    SPARSE_NAME: SparseVector(
                        indices=sparse_vec["indices"],
                        values=sparse_vec["values"],
                    ),
                },
                payload={
                    "type": "child",
                    "parent_id": chunk["parent_id"],
                    "doc_id": doc_id,
                    "filename": filename,
                    "r2_key": r2_key,
                    "text_snippet": chunk["text"][:500],
                    "page": chunk["page"],
                    "chunk_id": chunk["id"],
                },
            )
        )

    if points:
        client.upsert(COLLECTION_CHUNKS, points=points)


def search_chunks(
    query_dense: list[float],
    query_sparse: dict,
    top_k: int = 20,
) -> list[dict]:
    """Hybrid search (dense + sparse BM25, RRF fusion). No partition filter."""
    client = _client()
    _ensure_collection(client)

    results = client.query_points(
        collection_name=COLLECTION_CHUNKS,
        prefetch=[
            Prefetch(query=query_dense, using=DENSE_NAME, limit=top_k * 2),
            Prefetch(
                query=SparseVector(
                    indices=query_sparse["indices"],
                    values=query_sparse["values"],
                ),
                using=SPARSE_NAME,
                limit=top_k * 2,
            ),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_k,
        with_payload=True,
    )

    return [
        {
            "text_snippet": r.payload["text_snippet"],
            "parent_id": r.payload["parent_id"],
            "doc_id": r.payload.get("doc_id", ""),
            "filename": r.payload.get("filename", ""),
            "score": r.score,
        }
        for r in results.points
    ]


def fetch_parent(parent_id: str) -> dict | None:
    return fetch_parent_block(parent_id)
