from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Booking, BookingStatus, Review, User, UserRole
from tests.conftest import FakeArqPool


pytestmark = pytest.mark.asyncio

ADMIN_ID = UUID("00000000-0000-0000-0000-000000000001")
PROVIDER_ID = UUID("00000000-0000-0000-0000-000000000002")
CUSTOMER_ID = UUID("00000000-0000-0000-0000-000000000003")
OTHER_CUSTOMER_ID = UUID("00000000-0000-0000-0000-000000000004")


def auth_headers(user_id: UUID, role: UserRole) -> dict[str, str]:
    return {
        "X-User-ID": str(user_id),
        "X-User-Role": role.value,
    }


async def seed_users(session: AsyncSession) -> None:
    session.add_all(
        [
            User(
                id=ADMIN_ID,
                email="admin@test.local",
                full_name="Test Admin",
                role=UserRole.ADMIN,
            ),
            User(
                id=PROVIDER_ID,
                email="provider@test.local",
                full_name="Test Provider",
                role=UserRole.PROVIDER,
            ),
            User(
                id=CUSTOMER_ID,
                email="customer@test.local",
                full_name="Test Customer",
                role=UserRole.CUSTOMER,
            ),
            User(
                id=OTHER_CUSTOMER_ID,
                email="other-customer@test.local",
                full_name="Other Customer",
                role=UserRole.CUSTOMER,
            ),
        ]
    )
    await session.flush()


async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get(
        "/health",
        headers=auth_headers(ADMIN_ID, UserRole.ADMIN),
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "redis": "ok",
    }


async def test_customer_creates_booking_with_rbac_isolation(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await seed_users(db_session)
    start = datetime.now(timezone.utc) + timedelta(days=1)

    response = await client.post(
        "/bookings",
        headers=auth_headers(CUSTOMER_ID, UserRole.CUSTOMER),
        json={
            "provider_id": str(PROVIDER_ID),
            # A customer cannot impersonate another customer; the API replaces it.
            "customer_id": str(OTHER_CUSTOMER_ID),
            "service_name": "Assessment consultation",
            "scheduled_start": start.isoformat(),
            "scheduled_end": (start + timedelta(hours=1)).isoformat(),
            "price": "750.00",
            "currency": "inr",
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["customer_id"] == str(CUSTOMER_ID)
    assert created["provider_id"] == str(PROVIDER_ID)
    assert created["currency"] == "INR"

    owner_list = await client.get(
        "/bookings",
        headers=auth_headers(CUSTOMER_ID, UserRole.CUSTOMER),
    )
    other_list = await client.get(
        "/bookings",
        headers=auth_headers(OTHER_CUSTOMER_ID, UserRole.CUSTOMER),
    )

    assert owner_list.status_code == 200
    assert len(owner_list.json()) == 1
    assert other_list.status_code == 200
    assert other_list.json() == []


async def test_review_summary_is_authorized_and_enqueued(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_arq_pool: FakeArqPool,
) -> None:
    await seed_users(db_session)
    completed_at = datetime.now(timezone.utc)
    booking = Booking(
        id=uuid4(),
        provider_id=PROVIDER_ID,
        customer_id=CUSTOMER_ID,
        service_name="Completed assessment service",
        scheduled_start=completed_at - timedelta(hours=2),
        scheduled_end=completed_at - timedelta(hours=1),
        status=BookingStatus.COMPLETED,
        price=Decimal("1000.00"),
        currency="INR",
        completed_at=completed_at,
    )
    review = Review(
        id=uuid4(),
        booking=booking,
        rating=5,
        comment="A thoughtful and reliable service.",
    )
    db_session.add(review)
    await db_session.flush()

    forbidden = await client.post(
        f"/reviews/{review.id}/summarize",
        headers=auth_headers(OTHER_CUSTOMER_ID, UserRole.CUSTOMER),
    )
    response = await client.post(
        f"/reviews/{review.id}/summarize",
        headers=auth_headers(CUSTOMER_ID, UserRole.CUSTOMER),
    )

    assert forbidden.status_code == 403
    assert response.status_code == 202
    assert response.json() == {
        "review_id": str(review.id),
        "job_id": "test-summary-job",
        "status": "queued",
    }
    assert fake_arq_pool.enqueued_jobs == [
        ("summarize_review_task", (review.id.int,))
    ]

