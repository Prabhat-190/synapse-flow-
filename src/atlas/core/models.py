"""Typed domain models for the ATLAS orchestration pipeline."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentRole(StrEnum):
    ORCHESTRATOR = "orchestrator"
    DECOMPOSITION = "decomposition"
    RETRIEVAL = "retrieval"
    REASONING = "reasoning"
    CRITIQUE = "critique"
    SYNTHESIS = "synthesis"
    COMPRESSION = "compression"
    META = "meta"
    TOOL_EXECUTOR = "tool_executor"


class SpanAction(StrEnum):
    RESOLVE = "RESOLVE"
    REMOVE = "REMOVE"
    HEDGE = "HEDGE"
    KEEP = "KEEP"


class SynthesisAction(StrEnum):
    RESOLVE = "RESOLVE"
    REMOVE = "REMOVE"
    HEDGE = "HEDGE"


class EvalTier(StrEnum):
    BASELINE = "BASELINE"
    AMBIGUOUS = "AMBIGUOUS"
    ADVERSARIAL = "ADVERSARIAL"


class SubtaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Subtask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    agent: AgentRole
    dependencies: list[str] = Field(default_factory=list)
    status: SubtaskStatus = SubtaskStatus.PENDING
    result: dict[str, Any] | None = None
    priority: int = 0
    token_budget: int = 4096


class SubtaskDAG(BaseModel):
    """Typed directed acyclic graph of subtasks."""

    root_query: str
    nodes: list[Subtask] = Field(default_factory=list)

    def ready_nodes(self) -> list[Subtask]:
        completed = {n.id for n in self.nodes if n.status == SubtaskStatus.COMPLETED}
        return [
            n
            for n in self.nodes
            if n.status == SubtaskStatus.PENDING
            and all(dep in completed for dep in n.dependencies)
        ]

    def is_complete(self) -> bool:
        return all(n.status in (SubtaskStatus.COMPLETED, SubtaskStatus.SKIPPED) for n in self.nodes)


class Citation(BaseModel):
    doc_id: str
    chunk_id: str
    text: str
    score: float
    hop: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimSpan(BaseModel):
    span_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    start: int
    end: int
    confidence: float = 1.0
    citations: list[Citation] = Field(default_factory=list)
    flagged: bool = False
    flag_reason: str | None = None
    action: SpanAction = SpanAction.KEEP
    critique_score: float | None = None


class ProvenanceMap(BaseModel):
    """Sentence-level provenance tracking."""

    entries: dict[str, list[str]] = Field(default_factory=dict)

    def link(self, sentence: str, source_ids: list[str]) -> None:
        self.entries[sentence] = source_ids

    def get_sources(self, sentence: str) -> list[str]:
        return self.entries.get(sentence, [])


class RoutingDecision(BaseModel):
    next_agent: AgentRole
    reason: str
    confidence: float = 1.0
    fallback: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromptRewrite(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_prompt: str
    rewritten_prompt: str
    rationale: str
    approved: bool | None = None
    approved_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TraceEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    agent: AgentRole
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    token_count: int = 0


class AgentEvent(BaseModel):
    """Live SSE event published via Redis pub/sub."""

    run_id: str
    agent: AgentRole
    status: str
    message: str
    progress: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExecutionTrace(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    query: str
    events: list[TraceEvent] = Field(default_factory=list)
    final_answer: str | None = None
    provenance: ProvenanceMap = Field(default_factory=ProvenanceMap)
    citations: list[Citation] = Field(default_factory=list)
    spans: list[ClaimSpan] = Field(default_factory=list)
    dag: SubtaskDAG | None = None
    prompt_rewrites: list[PromptRewrite] = Field(default_factory=list)
    total_tokens: int = 0
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    status: str = "running"


class CompressionResult(BaseModel):
    original_tokens: int
    compressed_tokens: int
    mode: str  # "lossless" | "lossy"
    preserved_critical: list[str] = Field(default_factory=list)
    summary: str


class EvalCase(BaseModel):
    id: str
    tier: EvalTier
    query: str
    expected_behaviors: list[str] = Field(default_factory=list)
    ground_truth: str | None = None
    required_citations: bool = False


class EvalResult(BaseModel):
    case_id: str
    tier: EvalTier
    correctness: float
    citation_score: float
    contradiction_resolution: float
    tool_efficiency: float
    budget_compliance: float
    overall: float
    judge_rationale: str
    passed: bool
