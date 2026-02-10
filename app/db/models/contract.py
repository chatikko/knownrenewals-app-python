from datetime import date, timedelta

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Contract(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contracts"
    __table_args__ = (
        CheckConstraint("notice_period_days >= 0", name="notice_period_non_negative"),
        Index("ix_contracts_created_at", "created_at"),
    )

    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    renewal_type: Mapped[str] = mapped_column(
        Enum("Subscription", "Contract", "License", "Domain", "Certificate", "Other", name="renewal_type_enum"),
        nullable=False,
        default="Contract",
    )
    renewal_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    contract_name: Mapped[str | None] = mapped_column(String(255))
    renewal_date: Mapped[date] = mapped_column(nullable=False)
    notice_period_days: Mapped[int] = mapped_column(nullable=False, default=30)
    notice_deadline: Mapped[date] = mapped_column(nullable=False, index=True)
    owner_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        Enum("safe", "soon", "risk", name="contract_status_enum"),
        default="safe",
        nullable=False,
    )

    account = relationship("Account", back_populates="contracts")
    reminder_logs = relationship("ContractReminderLog", back_populates="contract", cascade="all, delete-orphan")

    @staticmethod
    def compute_notice_deadline(renewal_date: date, notice_period_days: int) -> date:
        return renewal_date - timedelta(days=notice_period_days)

    @validates("notice_period_days", "renewal_date")
    def _update_deadline(self, key: str, value):
        notice_period = value if key == "notice_period_days" else self.notice_period_days
        renewal_date = value if key == "renewal_date" else self.renewal_date

        if renewal_date and notice_period is not None:
            self.notice_deadline = self.compute_notice_deadline(renewal_date, notice_period)
        return value


class ContractReminderLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contract_reminder_logs"
    __table_args__ = (
        CheckConstraint("days_before >= 0", name="days_before_positive"),
        UniqueConstraint("contract_id", "reminder_date", "days_before", name="uq_contract_reminder"),
        Index("ix_contract_reminders_created_at", "created_at"),
    )

    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False)
    reminder_date: Mapped[date] = mapped_column(nullable=False)
    days_before: Mapped[int] = mapped_column(nullable=False)

    contract = relationship("Contract", back_populates="reminder_logs")


# Ensure Account is registered in the mapper registry when this module is imported.
from app.db.models.account import Account  # noqa: E402,F401
