import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class TransactionRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "records"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transaction_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    merchant_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="records")

    __table_args__ = (
        CheckConstraint(
            "category IN ('payment', 'transfer', 'refund', 'withdrawal', 'deposit')",
            name="ck_record_category",
        ),
        CheckConstraint(
            "status IN ('pending', 'cleared', 'flagged', 'rejected')",
            name="ck_record_status",
        ),
        CheckConstraint(
            "risk_score >= 0.0 AND risk_score <= 1.0",
            name="ck_record_risk_score",
        ),
        Index("ix_records_user_occurred", "user_id", occurred_at.desc()),
        Index("ix_records_user_status", "user_id", "status"),
        Index("ix_records_user_category", "user_id", "category"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_records_user_idempotency"),
    )

    def __repr__(self) -> str:
        return (
            f"<TransactionRecord id={self.id} txn={self.transaction_id} "
            f"amt={self.amount} {self.currency} status={self.status}>"
        )
