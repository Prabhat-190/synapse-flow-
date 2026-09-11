"""Reasoning agent — generates draft answer from retrieved context."""

from __future__ import annotations

from atlas.agents.base import BaseAgent
from atlas.core.blackboard import Blackboard
from atlas.core.models import AgentRole


class ReasoningAgent(BaseAgent):
    role = AgentRole.REASONING

    PROMPT = """You are a reasoning agent. Generate a comprehensive draft answer using ONLY the provided citations.

Query: {query}

Citations:
{citations}

Requirements:
- Cite sources inline as [doc_id]
- Do not make unsupported claims
- Be precise and technical

Draft answer:"""

    async def _run(self, blackboard: Blackboard) -> Blackboard:
        citations_text = "\n".join(
            f"[{c.doc_id}/{c.chunk_id}] (score={c.score:.2f}, hop={c.hop}): {c.text}"
            for c in blackboard.retrieved_docs
        )

        prompt = self.PROMPT.format(
            query=blackboard.trace.query,
            citations=citations_text or "No citations available.",
        )

        draft = await self._llm_call(blackboard, prompt)
        await blackboard.set_draft(draft)

        # Build initial provenance map
        for i, sentence in enumerate(draft.split(". ")):
            if sentence.strip():
                source_ids = [c.doc_id for c in blackboard.retrieved_docs[:2]]
                blackboard.provenance.link(sentence.strip(), source_ids)

        await blackboard.record_event(
            self.role,
            "draft_generated",
            {"length": len(draft), "citation_count": len(blackboard.retrieved_docs)},
        )
        return blackboard
