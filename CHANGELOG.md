# Changelog

All notable changes to SynapseFlow are documented in this file.

## [1.0.0] - 2026-09-11

### Added
- 8-agent LangGraph pipeline with shared context blackboard
- 2-hop RAG retrieval with pgvector and inline citations
- Critique-synthesis pipeline with RESOLVE / REMOVE / HEDGE span actions
- FastAPI gateway with API key auth, rate limiting, and prompt injection screening
- Redis pub/sub SSE streaming with PostgreSQL trace replay
- Celery worker for isolated async pipeline execution
- 15-case evaluation harness (BASELINE / AMBIGUOUS / ADVERSARIAL)
- Prometheus metrics, structured logging, Docker Compose stack
- CLI (`synapse query`, `synapse eval`, `synapse serve`)
- Project documentation PDF and README screenshots

### Fixed
- LLM mock routing false positives on synthesis prompts
- structlog initialization crash on server startup
- Redis graceful degradation when broker is unavailable
