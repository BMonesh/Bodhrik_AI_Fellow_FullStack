from typing import TypedDict, cast
from uuid import UUID

from fastapi import HTTPException, Request, status

from app.models.base import Booking, UserRole


class RequestUser(TypedDict):
    id: UUID
    role: str


def get_request_user(request: Request) -> RequestUser:
    return cast(RequestUser, request.state.user)


def ensure_booking_access(booking: Booking, user: RequestUser) -> None:
    """Allow admins or the provider/customer participating in the booking."""

    if user["role"] == UserRole.ADMIN.value:
        return
    if (
        user["role"] == UserRole.PROVIDER.value
        and booking.provider_id == user["id"]
    ):
        return
    if (
        user["role"] == UserRole.CUSTOMER.value
        and booking.customer_id == user["id"]
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this resource",
    )

