"""Retrieval agent — 2-hop pgvector search with inline citations."""

from __future__ import annotations

import json

from synapse.agents.base import BaseAgent
from synapse.core.blackboard import Blackboard
from synapse.core.models import AgentRole, Citation
from synapse.rag.embeddings import embed_text
from synapse.rag.two_hop import two_hop_search


class RetrievalAgent(BaseAgent):
    role = AgentRole.RETRIEVAL

    PROMPT = """Given these search results, select and rank the most relevant passages.

Query: {query}
Results: {results}

Respond with JSON: {{"selected": [{{"doc_id": "...", "chunk_id": "...", "text": "...", "score": 0.0-1.0}}]}}"""

    async def _run(self, blackboard: Blackboard) -> Blackboard:
        query = blackboard.trace.query

        # 2-hop vector search
        query_embedding = embed_text(query)
        hop1_results = await two_hop_search(query_embedding, query, hop=1, top_k=5)
        hop2_results = await two_hop_search(query_embedding, query, hop=2, top_k=3)

        all_results = hop1_results + hop2_results

        if not all_results:
            # LLM-assisted retrieval fallback
            response = await self._llm_call(
                blackboard,
                f"Search and retrieve relevant information for: {query}",
            )
            try:
                data = json.loads(response)
                all_results = data.get("results", [])
            except json.JSONDecodeError:
                all_results = []

        citations = [
            Citation(
                doc_id=r.get("doc_id", "unknown"),
                chunk_id=r.get("chunk_id", "unknown"),
                text=r.get("text", ""),
                score=r.get("score", 0.0),
                hop=r.get("hop", 1),
                metadata=r.get("metadata", {}),
            )
            for r in all_results
        ]

        await blackboard.add_citations(citations)
        await blackboard.record_event(
            self.role,
            "retrieval_complete",
            {
                "hop1_count": len(hop1_results),
                "hop2_count": len(hop2_results),
                "total_citations": len(citations),
            },
        )
        return blackboard
