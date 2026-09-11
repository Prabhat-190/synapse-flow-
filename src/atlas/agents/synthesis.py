"""Synthesis agent — RESOLVE/REMOVE/HEDGE flagged spans with provenance."""

from __future__ import annotations

from atlas.agents.base import BaseAgent
from atlas.core.blackboard import Blackboard
from atlas.core.models import AgentRole, SpanAction, SynthesisAction


class SynthesisAgent(BaseAgent):
    role = AgentRole.SYNTHESIS

    PROMPT = """Synthesize a final answer applying these span actions:
- RESOLVE: fix with supporting evidence
- REMOVE: delete unsupported claim
- HEDGE: add qualifier ("may", "likely", "according to")

Draft: {draft}

Flagged spans:
{flagged}

Citations:
{citations}

Produce the final polished answer with inline [n] citations:"""

    async def _run(self, blackboard: Blackboard) -> Blackboard:
        flagged = [
            s for s in blackboard.claim_spans if s.flagged
        ]

        for span in blackboard.claim_spans:
            if not span.flagged:
                span.action = SpanAction.KEEP
                continue

            if span.critique_score and span.critique_score < 0.3:
                span.action = SpanAction.REMOVE
            elif span.critique_score and span.critique_score < 0.6:
                span.action = SpanAction.HEDGE
            else:
                span.action = SpanAction.RESOLVE

        flagged_text = "\n".join(
            f"- [{s.action.value}] {s.text} (score={s.critique_score})"
            for s in flagged
        )

        citations_text = "\n".join(
            f"[{i+1}] {c.text} (doc={c.doc_id})"
            for i, c in enumerate(blackboard.retrieved_docs)
        )

        prompt = self.PROMPT.format(
            draft=blackboard.draft_answer,
            flagged=flagged_text or "None",
            citations=citations_text,
        )

        final = await self._llm_call(blackboard, prompt)

        # Apply deterministic span actions as post-processing
        final = self._apply_span_actions(final, blackboard)

        await blackboard.finalize(final)
        await blackboard.record_event(
            self.role,
            "synthesis_complete",
            {
                "actions": {
                    a.value: sum(1 for s in blackboard.claim_spans if s.action == a)
                    for a in SpanAction
                },
            },
        )
        return blackboard

    def _apply_span_actions(self, text: str, blackboard: Blackboard) -> str:
        for span in blackboard.claim_spans:
            if span.action == SpanAction.REMOVE and span.text in text:
                text = text.replace(span.text, "")
            elif span.action == SpanAction.HEDGE and span.text in text:
                hedged = f"It is likely that {span.text.lower()}"
                text = text.replace(span.text, hedged)

        # Attach citation references
        if blackboard.retrieved_docs and "[1]" not in text:
            refs = " ".join(f"[{i+1}]" for i in range(len(blackboard.retrieved_docs)))
            text = f"{text}\n\nSources: {refs}"

        return text.strip()
