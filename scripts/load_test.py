#!/usr/bin/env python3
"""Concurrent load test for SynapseFlow API — reports p50/p95/p99 latency."""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx

DEFAULT_URL = "http://127.0.0.1:8000/v1/query"
DEFAULT_KEY = "dev-secret-key-change-in-production"


async def _one_request(client: httpx.AsyncClient, query: str) -> float:
    start = time.perf_counter()
    resp = await client.post("/v1/query", json={"query": query})
    resp.raise_for_status()
    return time.perf_counter() - start


async def run_load_test(base_url: str, api_key: str, concurrency: int, requests: int) -> dict:
    latencies: list[float] = []
    errors = 0
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(
        base_url=base_url.rsplit("/v1", 1)[0],
        headers={"X-API-Key": api_key},
        timeout=120.0,
    ) as client:

        async def worker(i: int) -> None:
            nonlocal errors
            async with sem:
                try:
                    ms = await _one_request(client, f"Load test query #{i}: explain RAG")
                    latencies.append(ms * 1000)
                except Exception:
                    errors += 1

        await asyncio.gather(*[worker(i) for i in range(requests)])

    if not latencies:
        return {"error": "All requests failed", "failures": errors}

    latencies.sort()
    n = len(latencies)

    def percentile(p: float) -> float:
        idx = int(n * p / 100)
        return latencies[min(idx, n - 1)]

    duration = sum(latencies) / 1000
    return {
        "requests": requests,
        "concurrency": concurrency,
        "success": n,
        "failures": errors,
        "throughput_rps": round(n / max(duration, 0.001), 2),
        "latency_ms": {
            "p50": round(percentile(50), 1),
            "p95": round(percentile(95), 1),
            "p99": round(percentile(99), 1),
            "mean": round(statistics.mean(latencies), 1),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="SynapseFlow load test")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--key", default=DEFAULT_KEY)
    parser.add_argument("-c", "--concurrency", type=int, default=5)
    parser.add_argument("-n", "--requests", type=int, default=20)
    args = parser.parse_args()

    result = asyncio.run(run_load_test(args.url, args.key, args.concurrency, args.requests))
    print("\n=== SynapseFlow Load Test ===")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
