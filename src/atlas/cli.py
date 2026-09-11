"""CLI entry point for ATLAS orchestrator."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="ATLAS Multi-Agent Orchestrator")
    sub = parser.add_subparsers(dest="command")

    query_parser = sub.add_parser("query", help="Run a query through the pipeline")
    query_parser.add_argument("text", help="Query text")
    query_parser.add_argument("--json", action="store_true", help="Output as JSON")

    sub.add_parser("eval", help="Run the 15-case evaluation harness")
    sub.add_parser("serve", help="Start the FastAPI server")

    args = parser.parse_args()

    if args.command == "query":
        asyncio.run(_run_query(args.text, args.json))
    elif args.command == "eval":
        asyncio.run(_run_eval())
    elif args.command == "serve":
        _serve()
    else:
        parser.print_help()
        sys.exit(1)


async def _run_query(text: str, as_json: bool) -> None:
    from atlas.agents.pipeline import run_pipeline

    trace = await run_pipeline(text)
    if as_json:
        print(json.dumps(trace.model_dump(), indent=2, default=str))
    else:
        print(f"\n{'='*60}")
        print(f"Run ID: {trace.run_id}")
        print(f"Tokens: {trace.total_tokens}")
        print(f"Citations: {len(trace.citations)}")
        print(f"{'='*60}")
        print(trace.final_answer or "No answer generated")
        print(f"{'='*60}\n")


async def _run_eval() -> None:
    from atlas.eval.harness import EvalHarness

    harness = EvalHarness()
    results = await harness.run_all()
    summary = harness.summary()

    print(f"\n{'='*60}")
    print("EVALUATION RESULTS")
    print(f"{'='*60}")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.case_id} ({r.tier.value}): {r.overall:.2f}")
    print(f"\nSummary: {summary['passed']}/{summary['total']} passed, avg={summary['avg_overall']}")
    print(f"{'='*60}\n")


def _serve() -> None:
    import uvicorn

    uvicorn.run("atlas.gateway.app:app", host="0.0.0.0", port=8000, reload=True)
