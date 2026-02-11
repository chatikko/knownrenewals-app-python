from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.config import Settings
from app.db.models.account import Account


@dataclass
class BillingAccessState:
    status: str
    trial_days_left: int | None
    grace_days_left: int | None
    read_allowed: bool
    write_allowed: bool
    read_only_mode: bool
    trial_expired: bool


def resolve_billing_access_state(account: Account, settings: Settings) -> BillingAccessState:
    now = datetime.now(timezone.utc)
    status = (account.status or "").lower()

    if status == "active":
        return BillingAccessState(
            status="active",
            trial_days_left=None,
            grace_days_left=None,
            read_allowed=True,
            write_allowed=True,
            read_only_mode=False,
            trial_expired=False,
        )

    if status == "trialing":
        trial_end = _trial_end(account.created_at, settings.trial_period_days)
        trial_days_left = max(0, (trial_end.date() - now.date()).days)
        if now <= trial_end:
            return BillingAccessState(
                status="trialing",
                trial_days_left=trial_days_left,
                grace_days_left=settings.trial_grace_period_days,
                read_allowed=True,
                write_allowed=True,
                read_only_mode=False,
                trial_expired=False,
            )

        grace_end = trial_end + timedelta(days=settings.trial_grace_period_days)
        grace_days_left = max(0, (grace_end.date() - now.date()).days)
        if now <= grace_end:
            return BillingAccessState(
                status="past_due",
                trial_days_left=0,
                grace_days_left=grace_days_left,
                read_allowed=True,
                write_allowed=False,
                read_only_mode=True,
                trial_expired=True,
            )

        return BillingAccessState(
            status="past_due",
            trial_days_left=0,
            grace_days_left=0,
            read_allowed=False,
            write_allowed=False,
            read_only_mode=False,
            trial_expired=True,
        )

    return BillingAccessState(
        status=status or "inactive",
        trial_days_left=None,
        grace_days_left=None,
        read_allowed=False,
        write_allowed=False,
        read_only_mode=False,
        trial_expired=False,
    )


def _trial_end(created_at: datetime | None, trial_period_days: int) -> datetime:
    base = created_at or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base + timedelta(days=trial_period_days)
