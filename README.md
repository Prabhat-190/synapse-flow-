# ATLAS — Adaptive Typed LangGraph Agent System

Production-grade **multi-agent LLM orchestration** platform with 8 specialized agents, 2-hop RAG, critique-synthesis pipeline, and human-in-the-loop prompt optimization.

[![CI](https://github.com/Prabhat-190/atlas-orchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/Prabhat-190/atlas-orchestrator/actions)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Gateway                          │
│  Auth │ Rate Limit │ Injection Screen │ SSE Streaming      │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│              LangGraph Pipeline (8 Agents)                  │
│                                                             │
│  Orchestrator ──→ Decomposition ──→ Retrieval (2-hop RAG)  │
│       ↑              ↓                  ↓                   │
│       │         Subtask DAG        Citations                │
│       │              ↓                  ↓                   │
│       ├─── Reasoning ──→ Critique ──→ Synthesis            │
│       │    (draft)      (span scores)  (RESOLVE/REMOVE)     │
│       ├─── Compression (lossless/lossy on budget overflow)  │
│       └─── Meta (PromptRewrites, human approval gated)      │
│                                                             │
│              Shared Context Blackboard                      │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   PostgreSQL        Redis           Gemini
   (traces,          (pub/sub,        (primary +
    pgvector)          Celery)         fallback)
```

## Features

| Feature | Description |
|---------|-------------|
| **8-Agent Pipeline** | Orchestrator, Decomposition, Retrieval, Reasoning, Critique, Synthesis, Compression, Meta |
| **Shared Blackboard** | Thread-safe context with DAG, citations, spans, provenance |
| **2-Hop RAG** | pgvector search with document-link expansion for improved recall |
| **Critique → Synthesis** | Per-span scoring with RESOLVE/REMOVE/HEDGE actions |
| **Never-Silent-Truncation** | BudgetOverflowError routes to Compression agent |
| **Human-in-the-Loop** | Meta agent proposes PromptRewrites gated by approval |
| **Deterministic Fallback** | LLM routing with rule-based fallback on API failure |
| **SSE Streaming** | Live agent states via Redis pub/sub, PostgreSQL trace replay |
| **Prompt Injection Defense** | Pattern + heuristic screening at API boundary |
| **Eval Harness** | 15 cases (BASELINE/AMBIGUOUS/ADVERSARIAL) with judge model |
| **Observability** | Prometheus metrics, structlog, OpenTelemetry-ready |

## Quick Start

```bash
# Clone and install
git clone https://github.com/Prabhat-190/atlas-orchestrator.git
cd atlas-orchestrator
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run a query (works offline with mock LLM)
atlas query "Explain LangGraph multi-agent orchestration"

# Start API server
atlas serve
# → http://localhost:8000/docs

# Run evaluation harness
atlas eval
```

### Docker (full stack)

```bash
cp .env.example .env
docker compose up -d
curl -X POST http://localhost:8000/v1/query \
  -H "X-API-Key: dev-secret-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is RAG?"}'
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/query` | POST | Execute multi-agent pipeline |
| `/v1/runs/{id}` | GET | Retrieve execution trace |
| `/v1/runs/{id}/stream` | GET | SSE live agent events |
| `/v1/runs/{id}/dag` | GET | Subtask DAG visualization |
| `/v1/rewrites/approve` | POST | Human approval for prompt rewrites |
| `/v1/eval/run` | POST | Run 15-case evaluation harness |
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |

## Tech Stack

- **LangGraph** — Stateful agent graph with conditional routing
- **Gemini** — Primary LLM with circuit breaker and semantic cache
- **FastAPI** — Async API gateway with SSE
- **Celery + Redis** — Isolated task execution and pub/sub
- **PostgreSQL + pgvector** — Trace persistence and vector search
- **Prometheus** — Request/pipeline metrics

## Project Structure

```
src/atlas/
├── agents/          # 8 specialized agents + LangGraph pipeline
├── core/            # Blackboard, models, token budget, exceptions
├── gateway/         # FastAPI app, security, SSE
├── infra/           # LLM router, database, Redis, Celery
├── rag/             # Embeddings, 2-hop retrieval
└── eval/            # 15-case evaluation harness
```

## Evaluation

```
Tier          Cases  Dimensions
─────────────────────────────────
BASELINE        5    correctness, citations, accuracy
AMBIGUOUS       5    contextual inference, clarification
ADVERSARIAL     5    injection defense, contradiction, budget
```

Scored by independent judge model (no self-grading) on 5 dimensions with weighted overall score.

## License

MIT
