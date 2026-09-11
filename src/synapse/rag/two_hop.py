"""2-hop retrieval: initial vector search → expand via linked documents."""

from __future__ import annotations

import structlog

from synapse.infra.database import search_documents
from synapse.rag.embeddings import embed_text

logger = structlog.get_logger()

# In-memory knowledge base for offline operation
_KNOWLEDGE_BASE = [
    {
        "id": "c-1",
        "doc_id": "doc-langgraph",
        "content": "LangGraph enables stateful multi-agent workflows with cyclic graph support and shared state management.",
        "metadata": {"topic": "orchestration", "links": ["doc-pgvector"]},
    },
    {
        "id": "c-2",
        "doc_id": "doc-pgvector",
        "content": "pgvector provides efficient vector similarity search in PostgreSQL with HNSW indexing for sub-millisecond queries.",
        "metadata": {"topic": "database", "links": ["doc-rag"]},
    },
    {
        "id": "c-3",
        "doc_id": "doc-rag",
        "content": "Retrieval-Augmented Generation (RAG) combines vector search with LLM reasoning for grounded, citation-backed answers.",
        "metadata": {"topic": "rag", "links": ["doc-langgraph"]},
    },
    {
        "id": "c-4",
        "doc_id": "doc-celery",
        "content": "Celery provides distributed task queues for isolating agent execution from the API gateway with Redis as broker.",
        "metadata": {"topic": "infrastructure", "links": []},
    },
    {
        "id": "c-5",
        "doc_id": "doc-security",
        "content": "Prompt injection defense at the API boundary uses pattern matching and semantic scoring to block adversarial inputs.",
        "metadata": {"topic": "security", "links": []},
    },
    {
        "id": "c-6",
        "doc_id": "doc-budget",
        "content": "Never-silent-truncation policy routes BudgetOverflowError to a Compression agent for lossless or lossy context reduction.",
        "metadata": {"topic": "context", "links": ["doc-langgraph"]},
    },
]

# Pre-compute embeddings
for chunk in _KNOWLEDGE_BASE:
    chunk["embedding"] = embed_text(chunk["content"])


async def two_hop_search(
    query_embedding: list[float],
    query_text: str,
    hop: int = 1,
    top_k: int = 5,
) -> list[dict]:
    """
    Perform vector search with optional 2-hop expansion.

    Hop 1: Direct similarity search on query embedding.
    Hop 2: Expand results via linked documents in metadata.
    """
    if hop == 1:
        results = _search_in_memory(query_embedding, top_k)
        for r in results:
            r["hop"] = 1
        return results

    # Hop 2: get hop-1 results, then expand via links
    hop1 = _search_in_memory(query_embedding, top_k)
    hop2_results: list[dict] = []
    seen_ids: set[str] = {r["chunk_id"] for r in hop1}

    for result in hop1:
        links = result.get("metadata", {}).get("links", [])
        for link_doc in links:
            for chunk in _KNOWLEDGE_BASE:
                if chunk["doc_id"] == link_doc and chunk["id"] not in seen_ids:
                    hop2_results.append({
                        "doc_id": chunk["doc_id"],
                        "chunk_id": chunk["id"],
                        "text": chunk["content"],
                        "score": result["score"] * 0.8,
                        "hop": 2,
                        "metadata": chunk["metadata"],
                        "expanded_from": result["doc_id"],
                    })
                    seen_ids.add(chunk["id"])

    hop2_results.sort(key=lambda x: x["score"], reverse=True)
    return hop2_results[:top_k]


def _search_in_memory(query_embedding: list[float], top_k: int) -> list[dict]:
    import numpy as np

    query_vec = np.array(query_embedding)
    query_norm = np.linalg.norm(query_vec) or 1.0
    scored = []

    for chunk in _KNOWLEDGE_BASE:
        doc_vec = np.array(chunk["embedding"])
        doc_norm = np.linalg.norm(doc_vec) or 1.0
        score = float(np.dot(query_vec, doc_vec) / (query_norm * doc_norm))
        scored.append({
            "doc_id": chunk["doc_id"],
            "chunk_id": chunk["id"],
            "text": chunk["content"],
            "score": score,
            "metadata": chunk["metadata"],
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
