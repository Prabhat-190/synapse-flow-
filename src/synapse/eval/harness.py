"""Evaluation harness: 100+ cases across BASELINE, AMBIGUOUS, ADVERSARIAL tiers."""

from __future__ import annotations

import json

import structlog

from synapse.agents.pipeline import run_pipeline
from synapse.core.models import EvalCase, EvalResult, EvalTier
from synapse.eval.datasets import CORE_CASES, get_all_eval_cases
from synapse.infra.llm import LLMRouter

logger = structlog.get_logger()

EVAL_CASES: list[EvalCase] = get_all_eval_cases(include_generated=True)


JUDGE_PROMPT = """You are an independent judge evaluating a multi-agent system's output.
Do NOT grade your own work — evaluate objectively.

Case tier: {tier}
Query: {query}
Expected behaviors: {behaviors}
System answer: {answer}
Citations provided: {citations}
Flagged spans: {flagged}
Total tokens used: {tokens}

Score each dimension 0.0-1.0:
- correctness: factual accuracy
- citation_score: quality and relevance of citations
- contradiction_resolution: handling of conflicting/unsupported claims
- tool_efficiency: appropriate agent routing and resource use
- budget_compliance: staying within token budget

Respond with JSON:
{{"correctness": 0.0, "citation_score": 0.0, "contradiction_resolution": 0.0, "tool_efficiency": 0.0, "budget_compliance": 0.0, "rationale": "...", "passed": true/false}}"""


class EvalHarness:
    def __init__(self, cases: list[EvalCase] | None = None) -> None:
        self.judge = LLMRouter()
        self.results: list[EvalResult] = []
        self.cases = cases if cases is not None else CORE_CASES

    async def run_all(self) -> list[EvalResult]:
        logger.info("eval_started", case_count=len(self.cases))
        self.results = []

        for case in self.cases:
            result = await self._run_case(case)
            self.results.append(result)
            logger.info(
                "eval_case_complete",
                case_id=case.id,
                tier=case.tier.value,
                overall=result.overall,
                passed=result.passed,
            )

        return self.results

    async def _run_case(self, case: EvalCase) -> EvalResult:
        try:
            trace = await run_pipeline(case.query)
        except Exception as exc:
            return EvalResult(
                case_id=case.id,
                tier=case.tier,
                correctness=0.0,
                citation_score=0.0,
                contradiction_resolution=0.0,
                tool_efficiency=0.0,
                budget_compliance=0.0,
                overall=0.0,
                judge_rationale=f"Pipeline failed: {exc}",
                passed=False,
            )

        scores = await self._judge_evaluate(case, trace)
        overall = (
            scores["correctness"] * 0.3
            + scores["citation_score"] * 0.2
            + scores["contradiction_resolution"] * 0.2
            + scores["tool_efficiency"] * 0.15
            + scores["budget_compliance"] * 0.15
        )

        return EvalResult(
            case_id=case.id,
            tier=case.tier,
            correctness=scores["correctness"],
            citation_score=scores["citation_score"],
            contradiction_resolution=scores["contradiction_resolution"],
            tool_efficiency=scores["tool_efficiency"],
            budget_compliance=scores["budget_compliance"],
            overall=round(overall, 3),
            judge_rationale=scores.get("rationale", ""),
            passed=scores.get("passed", overall >= 0.6),
        )

    async def _judge_evaluate(self, case: EvalCase, trace) -> dict:
        prompt = JUDGE_PROMPT.format(
            tier=case.tier.value,
            query=case.query,
            behaviors=", ".join(case.expected_behaviors),
            answer=trace.final_answer or "No answer generated",
            citations=len(trace.citations),
            flagged=sum(1 for s in trace.spans if s.flagged),
            tokens=trace.total_tokens,
        )

        response = await self.judge.generate(prompt, system="You are an independent evaluation judge.")

        try:
            data = json.loads(response.text)
            required = {"correctness", "citation_score", "contradiction_resolution",
                        "tool_efficiency", "budget_compliance"}
            if not required.issubset(data.keys()):
                return self._heuristic_score(case, trace)
            return data
        except json.JSONDecodeError:
            return self._heuristic_score(case, trace)

    def _heuristic_score(self, case: EvalCase, trace) -> dict:
        has_answer = bool(trace.final_answer)
        has_citations = len(trace.citations) > 0
        flagged = sum(1 for s in trace.spans if s.flagged)
        within_budget = trace.total_tokens < 128_000

        correctness = 0.8 if has_answer else 0.0
        citation_score = 0.9 if has_citations else 0.3
        contradiction = 0.8 if flagged == 0 else 0.6
        tool_eff = 0.85 if len(trace.events) >= 4 else 0.5
        budget = 1.0 if within_budget else 0.3

        if case.tier == EvalTier.ADVERSARIAL:
            correctness = 0.7 if flagged > 0 or not has_citations else 0.5

        return {
            "correctness": correctness,
            "citation_score": citation_score,
            "contradiction_resolution": contradiction,
            "tool_efficiency": tool_eff,
            "budget_compliance": budget,
            "rationale": "Heuristic scoring (judge model unavailable)",
            "passed": (correctness + citation_score) / 2 >= 0.5,
        }

    def summary(self) -> dict:
        if not self.results:
            return {"total": 0}

        by_tier: dict[str, list[EvalResult]] = {}
        for r in self.results:
            by_tier.setdefault(r.tier.value, []).append(r)

        return {
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r.passed),
            "failed": sum(1 for r in self.results if not r.passed),
            "avg_overall": round(sum(r.overall for r in self.results) / len(self.results), 3),
            "by_tier": {
                tier: {
                    "count": len(results),
                    "passed": sum(1 for r in results if r.passed),
                    "avg_overall": round(sum(r.overall for r in results) / len(results), 3),
                }
                for tier, results in by_tier.items()
            },
        }
