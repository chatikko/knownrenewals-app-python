from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LeadMagnetDownload(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lead_magnet_downloads"
    __table_args__ = (
        Index("ix_lead_magnet_downloads_created_at", "created_at"),
        Index("ix_lead_magnet_downloads_normalized_email", "normalized_email"),
        Index("ix_lead_magnet_downloads_status", "status"),
    )

    magnet_key: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("pending", "sent", "failed", "skipped", name="lead_magnet_status_enum"),
        nullable=False,
        default="pending",
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    source_path: Mapped[str | None] = mapped_column(String(512))
    utm_source: Mapped[str | None] = mapped_column(String(255))
    utm_medium: Mapped[str | None] = mapped_column(String(255))
    utm_campaign: Mapped[str | None] = mapped_column(String(255))
    utm_term: Mapped[str | None] = mapped_column(String(255))
    utm_content: Mapped[str | None] = mapped_column(String(255))
    referrer: Mapped[str | None] = mapped_column(String(1024))
    user_agent: Mapped[str | None] = mapped_column(String(1024))
    ip_hash: Mapped[str | None] = mapped_column(String(128))
