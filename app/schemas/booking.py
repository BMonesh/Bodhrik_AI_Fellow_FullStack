from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.base import BookingStatus


class BookingBase(BaseModel):
    service_name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    scheduled_start: datetime
    scheduled_end: datetime
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)

    @field_validator("scheduled_start", "scheduled_end")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("booking timestamps must include a timezone")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_schedule(self) -> "BookingBase":
        if self.scheduled_end <= self.scheduled_start:
            raise ValueError("scheduled_end must be later than scheduled_start")
        return self


class BookingCreate(BookingBase):
    provider_id: UUID
    customer_id: UUID | None = None
    status: BookingStatus = BookingStatus.PENDING


class BookingUpdate(BaseModel):
    service_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    status: BookingStatus | None = None
    price: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2,
    )
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("scheduled_start", "scheduled_end")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("booking timestamps must include a timezone")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @model_validator(mode="after")
    def validate_schedule(self) -> "BookingUpdate":
        required_fields = {
            "service_name",
            "scheduled_start",
            "scheduled_end",
            "status",
            "price",
            "currency",
        }
        null_fields = {
            field_name
            for field_name in required_fields & self.model_fields_set
            if getattr(self, field_name) is None
        }
        if null_fields:
            raise ValueError(
                f"Fields cannot be null: {', '.join(sorted(null_fields))}"
            )
        if (
            self.scheduled_start is not None
            and self.scheduled_end is not None
            and self.scheduled_end <= self.scheduled_start
        ):
            raise ValueError("scheduled_end must be later than scheduled_start")
        return self


class BookingResponse(BookingBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_id: UUID
    customer_id: UUID
    status: BookingStatus
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
