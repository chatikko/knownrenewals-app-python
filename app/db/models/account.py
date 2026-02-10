from sqlalchemy import Enum, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Account(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (Index("ix_accounts_created_at", "created_at"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    plan_tier: Mapped[str] = mapped_column(Enum("founders", "pro", "team", name="plan_tier_enum"), default="pro")
    plan: Mapped[str] = mapped_column(Enum("monthly", "yearly", name="plan_enum"), default="monthly")
    status: Mapped[str] = mapped_column(
        Enum("inactive", "trialing", "active", "past_due", "canceled", name="account_status_enum"), default="inactive"
    )

    users = relationship("User", back_populates="account", cascade="all, delete-orphan")
    contracts = relationship("Contract", back_populates="account", cascade="all, delete-orphan")


# Ensure User is registered in the mapper registry when this module is imported.
from app.db.models.user import User  # noqa: E402,F401
