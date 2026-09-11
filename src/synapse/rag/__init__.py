"""RAG retrieval with 2-hop pgvector search."""

from synapse.rag.embeddings import embed_text
from synapse.rag.two_hop import two_hop_search

__all__ = ["embed_text", "two_hop_search"]
