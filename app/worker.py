import asyncio
from typing import Any
from uuid import UUID

from arq.connections import RedisSettings

from app.core.config import settings


async def summarize_review_task(ctx: dict[str, Any], review_id: int) -> None:
    """Simulate an asynchronous LLM review summarization request."""

    del ctx
    await asyncio.sleep(3)
    canonical_review_id = UUID(int=review_id)
    print(f"Successfully summarized review {canonical_review_id}", flush=True)


class WorkerSettings:
    functions = [summarize_review_task]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 10
    job_timeout = 30
    keep_result = 0
