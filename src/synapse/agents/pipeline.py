"""LangGraph pipeline wiring all 8 agents on shared blackboard."""

from __future__ import annotations

from typing import TypedDict

import structlog
from langgraph.graph import END, StateGraph

from synapse.agents.compression import CompressionAgent
from synapse.agents.critique import CritiqueAgent
from synapse.agents.decomposition import DecompositionAgent
from synapse.agents.meta import MetaAgent
from synapse.agents.orchestrator import OrchestratorAgent
from synapse.agents.reasoning import ReasoningAgent
from synapse.agents.retrieval import RetrievalAgent
from synapse.agents.synthesis import SynthesisAgent
from synapse.config import get_settings
from synapse.core.blackboard import Blackboard
from synapse.core.exceptions import BudgetOverflowError
from synapse.core.models import AgentRole, ExecutionTrace
from synapse.infra.database import load_trace, persist_trace

logger = structlog.get_logger()

PIPELINE_ORDER = [
    AgentRole.ORCHESTRATOR,
    AgentRole.DECOMPOSITION,
    AgentRole.RETRIEVAL,
    AgentRole.REASONING,
    AgentRole.CRITIQUE,
    AgentRole.SYNTHESIS,
    AgentRole.META,
]


class PipelineState(TypedDict):
    blackboard: Blackboard
    step: int
    error: str | None


def _agents():
    return {
        AgentRole.ORCHESTRATOR: OrchestratorAgent(),
        AgentRole.DECOMPOSITION: DecompositionAgent(),
        AgentRole.RETRIEVAL: RetrievalAgent(),
        AgentRole.REASONING: ReasoningAgent(),
        AgentRole.CRITIQUE: CritiqueAgent(),
        AgentRole.SYNTHESIS: SynthesisAgent(),
        AgentRole.COMPRESSION: CompressionAgent(),
        AgentRole.META: MetaAgent(),
    }


async def _run_step(state: PipelineState) -> PipelineState:
    agents = _agents()
    bb = state["blackboard"]
    step = state["step"]

    if step >= len(PIPELINE_ORDER):
        return state

    role = PIPELINE_ORDER[step]
    agent = agents[role]

    try:
        await agent.execute(bb)
    except BudgetOverflowError:
        compression = agents[AgentRole.COMPRESSION]
        await compression.execute(bb)

    state["step"] = step + 1
    return state


def _should_continue(state: PipelineState) -> str:
    if state["step"] >= len(PIPELINE_ORDER):
        return "end"
    return "continue"


def build_graph() -> StateGraph:
    graph = StateGraph(PipelineState)
    graph.add_node("execute", _run_step)
    graph.set_entry_point("execute")
    graph.add_conditional_edges("execute", _should_continue, {"continue": "execute", "end": END})
    return graph


async def run_pipeline(query: str, run_id: str | None = None) -> ExecutionTrace:
    settings = get_settings()

    blackboard = Blackboard(
        query=query,
        max_tokens=settings.max_context_tokens,
        never_silent_truncation=settings.never_silent_truncation,
    )
    if run_id:
        blackboard.trace.run_id = run_id

    logger.info("pipeline_started", run_id=blackboard.run_id, query=query[:100])

    graph = build_graph()
    compiled = graph.compile()

    initial_state: PipelineState = {
        "blackboard": blackboard,
        "step": 0,
        "error": None,
    }

    try:
        await compiled.ainvoke(initial_state)
    except Exception as exc:
        logger.error("pipeline_failed", error=str(exc))
        blackboard.trace.status = "failed"
        raise

    if not blackboard.trace.final_answer and blackboard.draft_answer:
        await blackboard.finalize(blackboard.draft_answer)

    trace = blackboard.trace

    try:
        await persist_trace(trace)
    except Exception as exc:
        logger.warning("trace_persist_failed", error=str(exc))

    logger.info(
        "pipeline_completed",
        run_id=trace.run_id,
        tokens=trace.total_tokens,
        citations=len(trace.citations),
    )
    return trace


async def resume_pipeline(run_id: str) -> ExecutionTrace:
    """Resume a failed or incomplete pipeline from the last checkpoint."""
    from synapse.infra.redis_bus import get_checkpoint

    existing = await load_trace(run_id)
    if existing is None:
        raise ValueError(f"Run {run_id} not found")

    if existing.status == "completed":
        return existing

    checkpoint = await get_checkpoint(run_id)
    logger.info(
        "pipeline_resume",
        run_id=run_id,
        checkpoint=bool(checkpoint),
        events=len(existing.events),
    )

    # Re-execute pipeline; checkpoint + trace events preserve prior progress
    return await run_pipeline(existing.query, run_id=run_id)
