"""Pipeline performance metrics aggregation."""

from __future__ import annotations

from prometheus_client import REGISTRY


def get_pipeline_metrics() -> dict:
    """Aggregate SynapseFlow pipeline metrics for /v1/metrics."""
    metrics: dict = {
        "pipelines": {"total": 0, "success": 0, "failed": 0},
        "requests": {},
        "latency_buckets": {},
    }

    for metric in REGISTRY.collect():
        name = metric.name
        for sample in metric.samples:
            if name == "synapse_pipeline_runs_total":
                status = sample.labels.get("status", "unknown")
                metrics["pipelines"][status] = int(sample.value)
                metrics["pipelines"]["total"] += int(sample.value)
            elif name == "synapse_requests_total":
                endpoint = sample.labels.get("endpoint", "unknown")
                status = sample.labels.get("status", "unknown")
                metrics["requests"].setdefault(endpoint, {})[status] = int(sample.value)

    return metrics
