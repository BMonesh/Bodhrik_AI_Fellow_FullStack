from dataclasses import dataclass
from uuid import UUID

from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.models.base import UserRole


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Trusted request context produced by the edge authentication layer."""

    id: UUID
    role: UserRole


class RBACMiddleware(BaseHTTPMiddleware):
    """Validate the assessment-scope identity headers for every request."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        user_id_header = request.headers.get("X-User-ID")
        user_role_header = request.headers.get("X-User-Role")

        if not user_id_header or not user_role_header:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "X-User-ID and X-User-Role headers are required"},
            )

        try:
            user_id = UUID(user_id_header)
        except ValueError:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "X-User-ID must be a valid UUID"},
            )

        try:
            role = UserRole(user_role_header.lower())
        except ValueError:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": "Invalid user role",
                    "allowed_roles": [allowed_role.value for allowed_role in UserRole],
                },
            )

        request.state.user = AuthenticatedUser(id=user_id, role=role)
        return await call_next(request)

