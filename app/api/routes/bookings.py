from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import ensure_booking_access, get_request_user
from app.db.session import get_db_session
from app.models.base import Booking, BookingStatus, UserRole
from app.schemas.booking import BookingCreate, BookingResponse, BookingUpdate


router = APIRouter(prefix="/bookings", tags=["bookings"])


async def get_booking_or_404(
    session: AsyncSession,
    booking_id: UUID,
) -> Booking:
    booking = await session.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )
    return booking


async def commit_booking(session: AsyncSession, booking: Booking) -> None:
    try:
        await session.commit()
        await session.refresh(booking)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The booking conflicts with existing data",
        ) from exc


@router.post("", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingCreate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Booking:
    user = get_request_user(request)
    booking_data = payload.model_dump()

    if user["role"] == UserRole.CUSTOMER.value:
        booking_data["customer_id"] = user["id"]
    elif user["role"] == UserRole.PROVIDER.value:
        # Providers may only create bookings assigned to themselves.
        booking_data["provider_id"] = user["id"]

    if booking_data["customer_id"] is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="customer_id is required for admin and provider requests",
        )
    if booking_data["provider_id"] == booking_data["customer_id"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provider and customer must be different users",
        )

    if booking_data["status"] == BookingStatus.COMPLETED:
        booking_data["completed_at"] = datetime.now(timezone.utc)

    booking = Booking(**booking_data)
    session.add(booking)
    await commit_booking(session, booking)
    return booking


@router.get("", response_model=list[BookingResponse])
async def list_bookings(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> list[Booking]:
    user = get_request_user(request)
    query: Select[tuple[Booking]] = select(Booking)

    if user["role"] == UserRole.PROVIDER.value:
        query = query.where(Booking.provider_id == user["id"])
    elif user["role"] == UserRole.CUSTOMER.value:
        query = query.where(Booking.customer_id == user["id"])

    result = await session.scalars(query.order_by(Booking.created_at.desc()))
    return list(result.all())


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(
    booking_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Booking:
    booking = await get_booking_or_404(session, booking_id)
    ensure_booking_access(booking, get_request_user(request))
    return booking


@router.patch("/{booking_id}", response_model=BookingResponse)
async def update_booking(
    booking_id: UUID,
    payload: BookingUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Booking:
    booking = await get_booking_or_404(session, booking_id)
    ensure_booking_access(booking, get_request_user(request))
    update_data = payload.model_dump(exclude_unset=True)

    scheduled_start = update_data.get("scheduled_start", booking.scheduled_start)
    scheduled_end = update_data.get("scheduled_end", booking.scheduled_end)
    if scheduled_end <= scheduled_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="scheduled_end must be later than scheduled_start",
        )

    new_status = update_data.get("status")
    if new_status == BookingStatus.COMPLETED:
        update_data["completed_at"] = booking.completed_at or datetime.now(timezone.utc)
    elif new_status is not None:
        update_data["completed_at"] = None

    for field, value in update_data.items():
        setattr(booking, field, value)

    await commit_booking(session, booking)
    return booking


@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_booking(
    booking_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    booking = await get_booking_or_404(session, booking_id)
    ensure_booking_access(booking, get_request_user(request))

    await session.delete(booking)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The booking cannot be deleted because it is still referenced",
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
