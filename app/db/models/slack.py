from datetime import datetime

from sqlalchemy import Boolean, Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SlackIntegration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "slack_integrations"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_slack_integrations_account"),
        Index("ix_slack_integrations_created_at", "created_at"),
    )

    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(255), nullable=False)
    workspace_name: Mapped[str] = mapped_column(String(255), nullable=False)
    bot_user_id: Mapped[str | None] = mapped_column(String(255))
    bot_access_token_encrypted: Mapped[str | None] = mapped_column(String(2048))
    bot_token_last4: Mapped[str | None] = mapped_column(String(16))
    default_channel_id: Mapped[str | None] = mapped_column(String(255))
    default_channel_name: Mapped[str | None] = mapped_column(String(255))
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    instant_risk_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    instant_due_7d_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    digest_hour_local: Mapped[int] = mapped_column(default=9, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_degraded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    last_error_message: Mapped[str | None] = mapped_column(String(1024))
    last_error_at: Mapped[datetime | None]
    connected_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    connected_at: Mapped[datetime | None]
    disconnected_at: Mapped[datetime | None]

    account = relationship("Account", back_populates="slack_integration")
    connected_by_user = relationship("User")


class SlackAlertState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "slack_alert_state"
    __table_args__ = (
        UniqueConstraint("account_id", "contract_id", "event_type", "event_date_key", name="uq_slack_alert_state"),
        Index("ix_slack_alert_state_created_at", "created_at"),
    )

    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(
        Enum("risk", "due_7d", "daily_digest", name="slack_alert_event_type_enum"),
        nullable=False,
    )
    event_date_key: Mapped[str] = mapped_column(String(32), nullable=False)
    sent_at: Mapped[datetime]
    message_ts: Mapped[str | None] = mapped_column(String(64))

    account = relationship("Account")
    contract = relationship("Contract")


class SlackDeliveryLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "slack_delivery_logs"
    __table_args__ = (Index("ix_slack_delivery_logs_created_at", "created_at"),)

    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.id", ondelete="SET NULL"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    http_status: Mapped[int | None]
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(String(1024))

    account = relationship("Account")
    contract = relationship("Contract")


# Ensure ORM dependencies are registered when this module is imported.
from app.db.models.account import Account  # noqa: E402,F401
from app.db.models.contract import Contract  # noqa: E402,F401
from app.db.models.user import User  # noqa: E402,F401
