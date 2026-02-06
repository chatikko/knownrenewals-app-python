from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BillingEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "billing_events"
    __table_args__ = (
        UniqueConstraint("stripe_event_id"),
        Index("ix_billing_events_created_at", "created_at"),
    )

    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    stripe_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="processed")
