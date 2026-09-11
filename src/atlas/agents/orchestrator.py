"""Orchestrator agent — LLM-driven routing with deterministic fallback."""

from __future__ import annotations

import json

from atlas.agents.base import BaseAgent
from atlas.core.blackboard import Blackboard
from atlas.core.models import AgentRole, RoutingDecision


class OrchestratorAgent(BaseAgent):
    role = AgentRole.ORCHESTRATOR

    ROUTING_PROMPT = """You are the Orchestrator for a multi-agent system.
Given the current state, decide which agent should run next.

Available agents: decomposition, retrieval, reasoning, critique, synthesis, compression, meta

Current query: {query}
Draft answer length: {draft_len}
Citations count: {citations}
Spans count: {spans}
Total tokens: {tokens}
Has DAG: {has_dag}
Compression needed: {needs_compression}

Respond with JSON: {{"next_agent": "<agent>", "reason": "<reason>", "confidence": 0.0-1.0}}"""

    # Deterministic fallback routing when LLM fails
    FALLBACK_ROUTES: list[tuple[str, AgentRole]] = [
        ("no_dag", AgentRole.DECOMPOSITION),
        ("no_citations", AgentRole.RETRIEVAL),
        ("no_draft", AgentRole.REASONING),
        ("no_spans", AgentRole.CRITIQUE),
        ("no_final", AgentRole.SYNTHESIS),
    ]

    async def _run(self, blackboard: Blackboard) -> Blackboard:
        decision = await self._route(blackboard)
        await blackboard.record_routing(decision)
        await blackboard.record_event(
            self.role,
            "routing_decision",
            decision.model_dump(),
        )
        blackboard.metadata["next_agent"] = decision.next_agent.value
        return blackboard

    async def route_next(self, blackboard: Blackboard) -> AgentRole:
        decision = await self._route(blackboard)
        await blackboard.record_routing(decision)
        return decision.next_agent

    async def _route(self, blackboard: Blackboard) -> RoutingDecision:
        needs_compression = blackboard.budget.should_compress(
            blackboard.trace.total_tokens,
            threshold=0.85,
        )

        prompt = self.ROUTING_PROMPT.format(
            query=blackboard.trace.query,
            draft_len=len(blackboard.draft_answer),
            citations=len(blackboard.retrieved_docs),
            spans=len(blackboard.claim_spans),
            tokens=blackboard.trace.total_tokens,
            has_dag=blackboard.dag is not None,
            needs_compression=needs_compression,
        )

        try:
            response = await self._llm_call(blackboard, prompt)
            data = json.loads(response)
            return RoutingDecision(
                next_agent=AgentRole(data["next_agent"]),
                reason=data.get("reason", "LLM routing"),
                confidence=data.get("confidence", 0.8),
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return self._deterministic_fallback(blackboard, needs_compression)

    def _deterministic_fallback(
        self,
        blackboard: Blackboard,
        needs_compression: bool,
    ) -> RoutingDecision:
        if needs_compression:
            return RoutingDecision(
                next_agent=AgentRole.COMPRESSION,
                reason="Budget threshold exceeded — deterministic fallback",
                confidence=1.0,
                fallback=True,
            )

        if blackboard.dag is None:
            return RoutingDecision(
                next_agent=AgentRole.DECOMPOSITION,
                reason="No task DAG — decompose first",
                confidence=1.0,
                fallback=True,
            )
        if not blackboard.retrieved_docs:
            return RoutingDecision(
                next_agent=AgentRole.RETRIEVAL,
                reason="No citations retrieved",
                confidence=1.0,
                fallback=True,
            )
        if not blackboard.draft_answer:
            return RoutingDecision(
                next_agent=AgentRole.REASONING,
                reason="No draft answer generated",
                confidence=1.0,
                fallback=True,
            )
        if not blackboard.claim_spans:
            return RoutingDecision(
                next_agent=AgentRole.CRITIQUE,
                reason="Claims not yet scored",
                confidence=1.0,
                fallback=True,
            )
        return RoutingDecision(
            next_agent=AgentRole.SYNTHESIS,
            reason="All prerequisites met — synthesize",
            confidence=1.0,
            fallback=True,
        )
