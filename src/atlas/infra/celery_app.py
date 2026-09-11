"""Celery task queue for isolated agent execution."""

from celery import Celery

from atlas.config import get_settings

settings = get_settings()

celery_app = Celery(
    "atlas",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_routes={"atlas.tasks.*": {"queue": "atlas.default"}},
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="atlas.tasks.run_pipeline", bind=True, max_retries=2)
def run_pipeline_task(self, query: str, run_id: str | None = None) -> dict:
    """Execute the full agent pipeline in an isolated worker process."""
    import asyncio

    from atlas.agents.pipeline import run_pipeline

    result = asyncio.get_event_loop().run_until_complete(run_pipeline(query, run_id))
    return result.model_dump()


@celery_app.task(name="atlas.tasks.run_eval")
def run_eval_task() -> dict:
    """Run the full evaluation harness."""
    import asyncio

    from atlas.eval.harness import EvalHarness

    harness = EvalHarness()
    results = asyncio.get_event_loop().run_until_complete(harness.run_all())
    return {"results": [r.model_dump() for r in results]}
