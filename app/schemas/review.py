from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ReviewSummaryJobResponse(BaseModel):
    review_id: UUID
    job_id: str
    status: Literal["queued"] = "queued"

