from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.api.routes.bookings import router as bookings_router
from app.api.routes.health import router as health_router
from app.core.config import settings
from app.core.middleware import RBACMiddleware
from app.db.redis import redis_client
from app.db.session import engine
from app.models.base import Base


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # create_all keeps this assessment self-starting. Use Alembic migrations in production.
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield

    await redis_client.aclose()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(RBACMiddleware)
app.include_router(health_router)
app.include_router(bookings_router)
