"""Critique agent — per-span claim scoring and flagging."""

from __future__ import annotations

import json

from synapse.agents.base import BaseAgent
from synapse.core.blackboard import Blackboard
from synapse.core.models import AgentRole, ClaimSpan, SpanAction


class CritiqueAgent(BaseAgent):
    role = AgentRole.CRITIQUE

    PROMPT = """Score each claim span for factual support. Flag unsupported claims.

Draft answer:
{draft}

Available citations:
{citations}

For each sentence, respond with JSON:
{{"spans": [{{"text": "...", "score": 0.0-1.0, "flagged": bool, "reason": "..."}}]}}

Score >= 0.7 = supported, < 0.7 = flagged."""

    async def _run(self, blackboard: Blackboard) -> Blackboard:
        citations_text = "\n".join(
            f"- {c.text} (score={c.score:.2f})" for c in blackboard.retrieved_docs
        )

        prompt = self.PROMPT.format(
            draft=blackboard.draft_answer,
            citations=citations_text or "None",
        )

        response = await self._llm_call(blackboard, prompt)
        spans = self._parse_spans(response, blackboard.draft_answer)

        await blackboard.set_spans(spans)
        flagged = sum(1 for s in spans if s.flagged)
        await blackboard.record_event(
            self.role,
            "critique_complete",
            {"total_spans": len(spans), "flagged_spans": flagged},
        )
        return blackboard

    def _parse_spans(self, response: str, draft: str) -> list[ClaimSpan]:
        try:
            data = json.loads(response)
            raw_spans = data.get("spans", [])
        except json.JSONDecodeError:
            raw_spans = []

        if not raw_spans:
            # Fallback: split draft into sentences
            raw_spans = [
                {"text": s.strip(), "score": 0.8, "flagged": False}
                for s in draft.split(". ")
                if s.strip()
            ]

        spans: list[ClaimSpan] = []
        offset = 0
        for raw in raw_spans:
            text = raw.get("text", "")
            start = draft.find(text, offset)
            if start == -1:
                start = offset
            end = start + len(text)
            offset = end

            score = raw.get("score", 0.5)
            flagged = raw.get("flagged", score < 0.7)

            spans.append(ClaimSpan(
                text=text,
                start=start,
                end=end,
                confidence=score,
                critique_score=score,
                flagged=flagged,
                flag_reason=raw.get("reason") if flagged else None,
                action=SpanAction.HEDGE if flagged else SpanAction.KEEP,
            ))

        return spans
