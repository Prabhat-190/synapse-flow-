"""Compression agent — lossless/lossy context compression on budget overflow."""

from __future__ import annotations

import json

from atlas.agents.base import BaseAgent
from atlas.core.blackboard import Blackboard
from atlas.core.models import AgentRole, CompressionResult


class CompressionAgent(BaseAgent):
    role = AgentRole.COMPRESSION

    PROMPT = """Compress the following context to reduce token count.

Mode: {mode}
Current tokens: {current_tokens}
Target reduction: {target_ratio}

Critical content (preserve exactly):
{critical}

Compressible content:
{compressible}

Respond with JSON: {{"summary": "...", "preserved": ["..."], "compressed_tokens": N}}"""

    CRITICAL_AGENTS = {AgentRole.ORCHESTRATOR, AgentRole.SYNTHESIS}

    async def _run(self, blackboard: Blackboard) -> Blackboard:
        current = blackboard.trace.total_tokens
        max_tokens = blackboard.budget.max_tokens
        utilization = blackboard.budget.utilization(current)

        mode = "lossless" if utilization < 0.95 else "lossy"

        critical_events = [
            e for e in blackboard.trace.events
            if e.agent in self.CRITICAL_AGENTS
        ]
        compressible_events = [
            e for e in blackboard.trace.events
            if e.agent not in self.CRITICAL_AGENTS
        ]

        critical_text = "\n".join(
            f"[{e.agent.value}] {e.event_type}: {json.dumps(e.payload)[:200]}"
            for e in critical_events
        )
        compressible_text = "\n".join(
            f"[{e.agent.value}] {e.event_type}: {json.dumps(e.payload)[:500]}"
            for e in compressible_events
        )

        target_ratio = 0.5 if mode == "lossy" else 0.8

        prompt = self.PROMPT.format(
            mode=mode,
            current_tokens=current,
            target_ratio=target_ratio,
            critical=critical_text[:2000],
            compressible=compressible_text[:4000],
        )

        response = await self._llm_call(blackboard, prompt)

        try:
            data = json.loads(response)
            summary = data.get("summary", response)
            compressed_tokens = data.get("compressed_tokens", int(current * target_ratio))
            preserved = data.get("preserved", [])
        except json.JSONDecodeError:
            summary = response[:1000]
            compressed_tokens = int(current * target_ratio)
            preserved = []

        result = CompressionResult(
            original_tokens=current,
            compressed_tokens=compressed_tokens,
            mode=mode,
            preserved_critical=preserved,
            summary=summary,
        )

        await blackboard.apply_compression(result)

        # Replace draft with compressed summary if lossy
        if mode == "lossy" and blackboard.draft_answer:
            blackboard.draft_answer = f"{summary}\n\n[Compressed from {current} tokens]"

        await blackboard.record_event(
            self.role,
            "compression_applied",
            {
                "mode": mode,
                "original_tokens": current,
                "compressed_tokens": compressed_tokens,
                "reduction": 1 - (compressed_tokens / max(current, 1)),
            },
        )
        return blackboard
