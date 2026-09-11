#!/usr/bin/env python3
"""Generate SynapseFlow project notes PDF."""

from pathlib import Path

from fpdf import FPDF

OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "SynapseFlow_Notes.pdf"


class NotesPDF(FPDF):
    def header(self) -> None:
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, "SynapseFlow - Project Notes", new_x="LMARGIN", new_y="NEXT", align="C")
        self.ln(4)

    def section(self, title: str) -> None:
        self.set_font("Helvetica", "B", 12)
        self.set_fill_color(230, 240, 255)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT", fill=True)
        self.ln(2)

    def body(self, text: str) -> None:
        self.set_font("Helvetica", "", 10)
        self.multi_cell(0, 5, text)
        self.ln(2)


def build_pdf() -> Path:
    pdf = NotesPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.section("Overview")
    pdf.body(
        "SynapseFlow is a production-grade multi-agent LLM orchestration platform. "
        "It coordinates 8 specialized agents through a shared context blackboard, "
        "with 2-hop RAG retrieval, critique-synthesis pipeline, budget compression, "
        "and human-in-the-loop prompt optimization."
    )

    pdf.section("Architecture")
    pdf.body(
        "FastAPI Gateway -> LangGraph Pipeline -> PostgreSQL / Redis / Gemini\n\n"
        "Agents: Orchestrator, Decomposition, Retrieval, Reasoning, Critique, "
        "Synthesis, Compression, Meta.\n\n"
        "The Orchestrator routes work using LLM decisions with deterministic fallback. "
        "Decomposition builds a typed subtask DAG. Retrieval performs 2-hop pgvector search. "
        "Critique scores claim spans; Synthesis applies RESOLVE/REMOVE/HEDGE actions."
    )

    pdf.section("Key Features")
    pdf.body(
        "- Shared context blackboard with thread-safe state\n"
        "- Never-silent-truncation budget policy\n"
        "- Prompt injection screening at API boundary\n"
        "- SSE streaming with PostgreSQL trace replay\n"
        "- 15-case eval harness (BASELINE / AMBIGUOUS / ADVERSARIAL)\n"
        "- Circuit breaker + semantic cache on LLM calls\n"
        "- Prometheus metrics and structured logging"
    )

    pdf.section("API Endpoints")
    pdf.body(
        "POST /v1/query          Execute multi-agent pipeline\n"
        "GET  /v1/runs/{id}      Retrieve execution trace\n"
        "GET  /v1/runs/{id}/stream   SSE live agent events\n"
        "GET  /v1/runs/{id}/dag  Subtask DAG visualization\n"
        "POST /v1/rewrites/approve   Human approval for rewrites\n"
        "POST /v1/eval/run       Run evaluation harness\n"
        "GET  /health            Health check\n"
        "GET  /metrics           Prometheus metrics"
    )

    pdf.section("Quick Start")
    pdf.body(
        "git clone https://github.com/Prabhat-190/synapse-flow-.git\n"
        "cd synapse-flow\n"
        "python -m venv .venv && source .venv/bin/activate\n"
        "pip install -e '.[dev]'\n"
        "synapse serve   # http://localhost:8000/docs\n"
        "synapse query 'Explain LangGraph orchestration'\n"
        "synapse eval"
    )

    pdf.section("Tech Stack")
    pdf.body(
        "LangGraph, Gemini, FastAPI, Celery, Redis, PostgreSQL, pgvector, "
        "Prometheus, structlog, OpenTelemetry-ready instrumentation."
    )

    pdf.section("Evaluation")
    pdf.body(
        "15 test cases across 3 tiers scored by an independent judge model on: "
        "correctness, citation quality, contradiction resolution, tool efficiency, "
        "and budget compliance."
    )

    pdf.section("Author")
    pdf.body("Prabhat Kumar - https://github.com/Prabhat-190")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUTPUT))
    return OUTPUT


if __name__ == "__main__":
    path = build_pdf()
    print(f"Generated: {path}")
