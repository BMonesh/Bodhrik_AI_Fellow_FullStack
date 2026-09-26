import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DDL,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def enum_values(enum_class: type[enum.Enum]) -> list[str]:
    """Persist enum values instead of Python member names."""

    return [str(member.value) for member in enum_class]


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    PROVIDER = "provider"
    CUSTOMER = "customer"


class BookingStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=enum_values), index=True
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")

    provider_bookings: Mapped[list["Booking"]] = relationship(
        back_populates="provider",
        foreign_keys="Booking.provider_id",
    )
    customer_bookings: Mapped[list["Booking"]] = relationship(
        back_populates="customer",
        foreign_keys="Booking.customer_id",
    )


class Booking(TimestampMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint(
            "provider_id <> customer_id", name="ck_booking_distinct_participants"
        ),
        CheckConstraint(
            "scheduled_end > scheduled_start", name="ck_booking_valid_schedule"
        ),
        CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL) OR "
            "(status <> 'completed' AND completed_at IS NULL)",
            name="ck_booking_completion_timestamp",
        ),
        Index("ix_bookings_provider_schedule", "provider_id", "scheduled_start"),
        Index("ix_bookings_customer_schedule", "customer_id", "scheduled_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    service_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status", values_callable=enum_values),
        default=BookingStatus.PENDING,
        server_default=BookingStatus.PENDING.value,
        index=True,
    )
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    provider: Mapped[User] = relationship(
        back_populates="provider_bookings", foreign_keys=[provider_id]
    )
    customer: Mapped[User] = relationship(
        back_populates="customer_bookings", foreign_keys=[customer_id]
    )
    review: Mapped["Review | None"] = relationship(
        back_populates="booking",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class Review(TimestampMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_rating_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)

    booking: Mapped[Booking] = relationship(back_populates="review")


# Cross-table CHECK constraints are not supported by PostgreSQL. These triggers
# preserve normalization (Review stores only booking_id) while enforcing that a
# review can only point to a completed booking, and that a reviewed booking can
# never be moved back to a non-completed state.
_review_integrity_ddl = (
    """
    CREATE OR REPLACE FUNCTION enforce_completed_review_booking()
    RETURNS trigger AS $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM bookings
            WHERE id = NEW.booking_id AND status = 'completed'
        ) THEN
            RAISE EXCEPTION 'reviews require a completed booking';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS trg_review_completed_booking ON reviews",
    """
    CREATE TRIGGER trg_review_completed_booking
    BEFORE INSERT OR UPDATE OF booking_id ON reviews
    FOR EACH ROW EXECUTE FUNCTION enforce_completed_review_booking()
    """,
    """
    CREATE OR REPLACE FUNCTION prevent_reviewed_booking_reopen()
    RETURNS trigger AS $$
    BEGIN
        IF NEW.status <> 'completed'
           AND EXISTS (SELECT 1 FROM reviews WHERE booking_id = NEW.id) THEN
            RAISE EXCEPTION 'a reviewed booking must remain completed';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS trg_reviewed_booking_stays_completed ON bookings",
    """
    CREATE TRIGGER trg_reviewed_booking_stays_completed
    BEFORE UPDATE OF status ON bookings
    FOR EACH ROW EXECUTE FUNCTION prevent_reviewed_booking_reopen()
    """,
)

for statement in _review_integrity_ddl:
    event.listen(
        Base.metadata,
        "after_create",
        DDL(statement).execute_if(dialect="postgresql"),
    )
