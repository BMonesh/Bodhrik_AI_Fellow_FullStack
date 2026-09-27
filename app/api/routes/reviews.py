from uuid import UUID

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.queue import get_arq_pool
from app.core.rbac import ensure_booking_access, get_request_user
from app.db.session import get_db_session
from app.models.base import Review
from app.schemas.review import ReviewSummaryJobResponse


router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post(
    "/{review_id}/summarize",
    response_model=ReviewSummaryJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_review_summary(
    review_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    queue: ArqRedis = Depends(get_arq_pool),
) -> ReviewSummaryJobResponse:
    query = (
        select(Review)
        .options(joinedload(Review.booking))
        .where(Review.id == review_id)
    )
    review = await session.scalar(query)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found",
        )

    ensure_booking_access(review.booking, get_request_user(request))

    try:
        # Review IDs are UUIDs in the domain model; UUID.int is lossless and
        # preserves the requested integer task signature.
        job = await queue.enqueue_job("summarize_review_task", review_id.int)
    except (OSError, RedisError, TimeoutError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to enqueue the review summary",
        ) from exc

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The review summary job was not accepted",
        )

    return ReviewSummaryJobResponse(review_id=review_id, job_id=job.job_id)

