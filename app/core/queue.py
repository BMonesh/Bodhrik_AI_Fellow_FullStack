import logging

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from app.core.config import settings


logger = logging.getLogger(__name__)


async def initialize_arq_pool() -> ArqRedis | None:
    """Create the producer pool without making API startup depend on Redis."""

    try:
        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        await pool.ping()
        logger.info("ARQ producer pool initialized")
        return pool
    except (OSError, RedisError, TimeoutError):
        logger.exception("ARQ producer pool initialization failed")
        return None


async def close_arq_pool(pool: ArqRedis | None) -> None:
    if pool is not None:
        await pool.aclose()


def get_arq_pool(request: Request) -> ArqRedis:
    pool: ArqRedis | None = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Background job queue is unavailable",
        )
    return pool

