"""Meta agent — proposes PromptRewrites gated by human approval."""

from __future__ import annotations

import json

from synapse.agents.base import BaseAgent
from synapse.core.blackboard import Blackboard
from synapse.core.models import AgentRole, PromptRewrite


class MetaAgent(BaseAgent):
    role = AgentRole.META

    PROMPT = """Analyze the query and system performance. Propose a prompt rewrite if beneficial.

Original query: {query}
Final answer quality indicators:
- Citations: {citations}
- Flagged spans: {flagged}
- Total tokens: {tokens}

Respond with JSON:
{{"rewritten_prompt": "...", "rationale": "...", "expected_improvement": "..."}}

Only propose rewrite if there's clear improvement opportunity."""

    async def _run(self, blackboard: Blackboard) -> Blackboard:
        flagged = sum(1 for s in blackboard.claim_spans if s.flagged)

        prompt = self.PROMPT.format(
            query=blackboard.trace.query,
            citations=len(blackboard.retrieved_docs),
            flagged=flagged,
            tokens=blackboard.trace.total_tokens,
        )

        response = await self._llm_call(blackboard, prompt)

        try:
            data = json.loads(response)
            rewrite = PromptRewrite(
                original_prompt=blackboard.trace.query,
                rewritten_prompt=data.get("rewritten_prompt", blackboard.trace.query),
                rationale=data.get("rationale", "No rationale provided"),
                approved=None,  # Requires human approval
            )
        except json.JSONDecodeError:
            rewrite = PromptRewrite(
                original_prompt=blackboard.trace.query,
                rewritten_prompt=blackboard.trace.query,
                rationale="No rewrite needed",
                approved=True,
            )

        await blackboard.add_rewrite(rewrite)
        await blackboard.record_event(
            self.role,
            "rewrite_proposed",
            {
                "rewrite_id": rewrite.id,
                "approved": rewrite.approved,
                "rationale": rewrite.rationale,
            },
        )
        return blackboard

    async def approve_rewrite(
        self,
        blackboard: Blackboard,
        rewrite_id: str,
        approved: bool,
        approved_by: str = "human",
    ) -> PromptRewrite | None:
        for rewrite in blackboard.pending_rewrites:
            if rewrite.id == rewrite_id:
                rewrite.approved = approved
                rewrite.approved_by = approved_by
                await blackboard.record_event(
                    self.role,
                    "rewrite_decision",
                    {"rewrite_id": rewrite_id, "approved": approved},
                )
                return rewrite
        return None
