"""FastAPI gateway with SSE streaming, health checks, and metrics."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from synapse.agents.meta import MetaAgent
from synapse.agents.pipeline import run_pipeline
from synapse.config import get_settings
from synapse.core.blackboard import Blackboard
from synapse.core.exceptions import BudgetOverflowError, PromptInjectionError
from synapse.gateway.security import check_rate_limit, screen_prompt_injection, verify_api_key
from synapse.infra.database import get_trace_events_since, init_db, load_trace

logger = structlog.get_logger()

REQUEST_COUNT = Counter("synapse_requests_total", "Total API requests", ["endpoint", "status"])
REQUEST_LATENCY = Histogram("synapse_request_latency_seconds", "Request latency", ["endpoint"])
PIPELINE_RUNS = Counter("synapse_pipeline_runs_total", "Pipeline executions", ["status"])


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000)
    run_id: str | None = None
    async_mode: bool = False


class RewriteApproval(BaseModel):
    run_id: str
    rewrite_id: str
    approved: bool
    approved_by: str = "human"


class HealthResponse(BaseModel):
    status: str
    version: str
    components: dict[str, str]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
    )
    try:
        await init_db()
        logger.info("database_initialized")
    except Exception as exc:
        logger.warning("database_init_skipped", error=str(exc))
    yield


app = FastAPI(
    title="SynapseFlow Orchestrator",
    description="Structured Intelligence Network for Agent Pipeline Execution — Multi-Agent LLM Orchestration",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(PromptInjectionError)
async def injection_handler(request: Request, exc: PromptInjectionError):
    REQUEST_COUNT.labels(endpoint="query", status="blocked").inc()
    return JSONResponse(
        status_code=400,
        content={"error": "prompt_injection_detected", "score": exc.score, "patterns": exc.patterns},
    )


@app.exception_handler(BudgetOverflowError)
async def budget_handler(request: Request, exc: BudgetOverflowError):
    return JSONResponse(
        status_code=413,
        content={
            "error": "budget_overflow",
            "current_tokens": exc.current_tokens,
            "max_tokens": exc.max_tokens,
            "action": "Routed to Compression agent",
        },
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        components={
            "api": "up",
            "pipeline": "ready",
            "database": "connected",
            "redis": "connected",
        },
    )


@app.get("/metrics")
async def metrics():
    return generate_latest()


@app.post("/v1/query")
async def query(
    req: QueryRequest,
    api_key: str = Depends(verify_api_key),
):
    check_rate_limit(api_key)
    screen_prompt_injection(req.query)

    if req.async_mode:
        from synapse.infra.celery_app import run_pipeline_task

        task = run_pipeline_task.delay(req.query, req.run_id)
        REQUEST_COUNT.labels(endpoint="query", status="accepted").inc()
        return {"task_id": task.id, "status": "queued"}

    with REQUEST_LATENCY.labels(endpoint="query").time():
        try:
            trace = await run_pipeline(req.query, req.run_id)
            PIPELINE_RUNS.labels(status="success").inc()
            REQUEST_COUNT.labels(endpoint="query", status="success").inc()
            return trace.model_dump()
        except Exception as exc:
            PIPELINE_RUNS.labels(status="failed").inc()
            REQUEST_COUNT.labels(endpoint="query", status="error").inc()
            raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/v1/runs/{run_id}")
async def get_run(run_id: str, api_key: str = Depends(verify_api_key)):
    trace = await load_trace(run_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return trace.model_dump()


@app.get("/v1/runs/{run_id}/stream")
async def stream_run(run_id: str, api_key: str = Depends(verify_api_key)):
    """SSE stream of live agent events with PostgreSQL trace reconstruction on reconnect."""

    async def event_generator():
        from synapse.infra.redis_bus import subscribe_events

        last_index = 0

        # Replay persisted events first (reconnection support)
        persisted = await get_trace_events_since(run_id, last_index)
        for event in persisted:
            yield {"event": "trace", "data": json.dumps(event.model_dump(), default=str)}
            last_index += 1

        # Stream live events via Redis pub/sub
        try:
            async for agent_event in subscribe_events(run_id):
                yield {"event": "agent", "data": agent_event.model_dump_json()}
        except asyncio.CancelledError:
            return

    return EventSourceResponse(event_generator())


@app.get("/v1/runs/{run_id}/dag")
async def get_dag(run_id: str, api_key: str = Depends(verify_api_key)):
    trace = await load_trace(run_id)
    if trace is None or trace.dag is None:
        raise HTTPException(status_code=404, detail="DAG not found")
    return trace.dag.model_dump()


@app.post("/v1/rewrites/approve")
async def approve_rewrite(req: RewriteApproval, api_key: str = Depends(verify_api_key)):
    trace = await load_trace(req.run_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Run not found")

    blackboard = Blackboard(query=trace.query)
    blackboard.trace = trace
    blackboard.pending_rewrites = trace.prompt_rewrites

    meta = MetaAgent()
    result = await meta.approve_rewrite(
        blackboard, req.rewrite_id, req.approved, req.approved_by
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Rewrite not found")

    return result.model_dump()


@app.post("/v1/eval/run")
async def run_evaluation(api_key: str = Depends(verify_api_key)):
    from synapse.eval.harness import EvalHarness

    harness = EvalHarness()
    results = await harness.run_all()
    return {"results": [r.model_dump() for r in results], "summary": harness.summary()}
