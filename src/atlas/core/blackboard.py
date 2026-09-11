"""Shared context blackboard — thread-safe state for multi-agent coordination."""

from __future__ import annotations

import asyncio
from typing import Any

from atlas.core.exceptions import BudgetOverflowError
from atlas.core.models import (
    AgentRole,
    Citation,
    ClaimSpan,
    CompressionResult,
    ExecutionTrace,
    PromptRewrite,
    ProvenanceMap,
    RoutingDecision,
    SubtaskDAG,
    TraceEvent,
)
from atlas.core.token_budget import TokenBudget


class Blackboard:
    """
    Central shared memory for the 7-agent pipeline.

    All agents read/write through this blackboard. State mutations are
    serialized via asyncio.Lock for concurrent-safe access in async context.
    """

    def __init__(
        self,
        query: str,
        max_tokens: int = 128_000,
        never_silent_truncation: bool = True,
    ) -> None:
        self.trace = ExecutionTrace(query=query)
        self.budget = TokenBudget(max_tokens=max_tokens)
        self.never_silent_truncation = never_silent_truncation
        self._lock = asyncio.Lock()

        # Working memory
        self.dag: SubtaskDAG | None = None
        self.retrieved_docs: list[Citation] = []
        self.draft_answer: str = ""
        self.claim_spans: list[ClaimSpan] = []
        self.provenance: ProvenanceMap = ProvenanceMap()
        self.compression_history: list[CompressionResult] = []
        self.pending_rewrites: list[PromptRewrite] = []
        self.routing_history: list[RoutingDecision] = []
        self.metadata: dict[str, Any] = {}

    @property
    def run_id(self) -> str:
        return self.trace.run_id

    async def record_event(
        self,
        agent: AgentRole,
        event_type: str,
        payload: dict[str, Any] | None = None,
        token_count: int = 0,
    ) -> TraceEvent:
        async with self._lock:
            if token_count > 0:
                await self._check_budget(token_count)

            event = TraceEvent(
                run_id=self.run_id,
                agent=agent,
                event_type=event_type,
                payload=payload or {},
                token_count=token_count,
            )
            self.trace.events.append(event)
            self.trace.total_tokens += token_count
            return event

    async def _check_budget(self, additional_tokens: int) -> None:
        projected = self.trace.total_tokens + additional_tokens
        if projected > self.budget.max_tokens:
            if self.never_silent_truncation:
                raise BudgetOverflowError(projected, self.budget.max_tokens)
            # Legacy path — we never take this when policy is enforced
            self.budget.mark_overflow(projected)

    async def set_dag(self, dag: SubtaskDAG) -> None:
        async with self._lock:
            self.dag = dag
            self.trace.dag = dag

    async def add_citations(self, citations: list[Citation]) -> None:
        async with self._lock:
            self.retrieved_docs.extend(citations)
            self.trace.citations = self.retrieved_docs

    async def set_draft(self, draft: str) -> None:
        async with self._lock:
            self.draft_answer = draft

    async def set_spans(self, spans: list[ClaimSpan]) -> None:
        async with self._lock:
            self.claim_spans = spans
            self.trace.spans = spans

    async def record_routing(self, decision: RoutingDecision) -> None:
        async with self._lock:
            self.routing_history.append(decision)

    async def add_rewrite(self, rewrite: PromptRewrite) -> None:
        async with self._lock:
            self.pending_rewrites.append(rewrite)
            self.trace.prompt_rewrites.append(rewrite)

    async def apply_compression(self, result: CompressionResult) -> None:
        async with self._lock:
            self.compression_history.append(result)
            self.trace.total_tokens = result.compressed_tokens

    async def finalize(self, answer: str) -> ExecutionTrace:
        from datetime import UTC, datetime

        async with self._lock:
            self.trace.final_answer = answer
            self.trace.provenance = self.provenance
            self.trace.completed_at = datetime.now(UTC)
            self.trace.status = "completed"
            return self.trace.model_copy(deep=True)

    def snapshot(self) -> dict[str, Any]:
        """Point-in-time snapshot for SSE streaming."""
        return {
            "run_id": self.run_id,
            "query": self.trace.query,
            "status": self.trace.status,
            "total_tokens": self.trace.total_tokens,
            "budget_remaining": self.budget.remaining(self.trace.total_tokens),
            "agents_completed": len({e.agent for e in self.trace.events}),
            "citations_count": len(self.retrieved_docs),
            "spans_count": len(self.claim_spans),
            "draft_length": len(self.draft_answer),
        }
