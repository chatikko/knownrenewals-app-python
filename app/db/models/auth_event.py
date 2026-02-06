from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuthEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "auth_events"
    __table_args__ = (Index("ix_auth_events_created_at", "created_at"),)

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    success: Mapped[bool] = mapped_column(default=True)

    user = relationship("User", back_populates="auth_events")
