import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://service_booking:service_booking@localhost:5432/"
    "service_booking_test",
)
if not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
    raise RuntimeError("TEST_DATABASE_URL must point to a database ending in '_test'")

# These must be set before importing app.main, which constructs application-level
# clients and engines at import time.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")

from app.api.routes.health import get_redis_client  # noqa: E402
from app.core.queue import get_arq_pool  # noqa: E402
from app.db.session import get_db_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import Base  # noqa: E402


test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
TestSessionFactory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    join_transaction_mode="create_savepoint",
)


class FakeRedis:
    async def ping(self) -> bool:
        return True


@dataclass(slots=True)
class FakeJob:
    job_id: str


class FakeArqPool:
    def __init__(self) -> None:
        self.enqueued_jobs: list[tuple[str, tuple[Any, ...]]] = []

    async def enqueue_job(self, function: str, *args: Any) -> FakeJob:
        self.enqueued_jobs.append((function, args))
        return FakeJob(job_id="test-summary-job")


@pytest_asyncio.fixture(scope="session", autouse=True, loop_scope="session")
async def prepare_test_database() -> AsyncIterator[None]:
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        session = TestSessionFactory(bind=connection)

        async def override_db_session() -> AsyncIterator[AsyncSession]:
            yield session

        app.dependency_overrides[get_db_session] = override_db_session
        try:
            yield session
        finally:
            app.dependency_overrides.pop(get_db_session, None)
            await session.close()
            await transaction.rollback()


@pytest_asyncio.fixture
async def fake_arq_pool() -> FakeArqPool:
    return FakeArqPool()


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    fake_arq_pool: FakeArqPool,
) -> AsyncIterator[AsyncClient]:
    del db_session

    app.dependency_overrides[get_redis_client] = lambda: FakeRedis()
    app.dependency_overrides[get_arq_pool] = lambda: fake_arq_pool
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client

    app.dependency_overrides.pop(get_redis_client, None)
    app.dependency_overrides.pop(get_arq_pool, None)
