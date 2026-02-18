from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError

from app.db.models.account import Account
from app.db.models.contract import Contract, ContractReminderLog
from app.db.session import async_session_factory
from app.services.email import email_service
from celery_app import celery_app

REMINDER_WINDOWS = (30, 14, 7)
REMINDER_ELIGIBLE_ACCOUNT_STATUSES = {"trialing", "active", "past_due"}


def _resolve_timezone(tz_name: str | None) -> ZoneInfo:
    if not tz_name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _today_for_timezone(tz_name: str | None, now_utc: datetime | None = None) -> date:
    now = now_utc or datetime.now(timezone.utc)
    return now.astimezone(_resolve_timezone(tz_name)).date()


@celery_app.task(name="app.tasks.reminders.schedule_notice_reminders")
def schedule_notice_reminders() -> None:
    asyncio.run(_schedule_notice_reminders())


@celery_app.task(name="app.tasks.reminders.send_contract_reminder")
def send_contract_reminder(contract_id: str, days_before: int) -> None:
    asyncio.run(_send_contract_reminder(contract_id, days_before))


async def _schedule_notice_reminders() -> None:
    async with async_session_factory() as session:
        now_utc = datetime.now(timezone.utc)
        account_rows = await session.execute(select(Account.id, Account.timezone, Account.status))
        for account_id, account_timezone, account_status in account_rows:
            normalized_status = (account_status or "").lower()
            if normalized_status not in REMINDER_ELIGIBLE_ACCOUNT_STATUSES:
                continue

            account_today = _today_for_timezone(account_timezone, now_utc)
            for window in REMINDER_WINDOWS:
                target_date = account_today + timedelta(days=window)
                contract_rows = await session.execute(
                    select(Contract.id).where(
                        Contract.account_id == account_id,
                        Contract.notice_deadline == target_date,
                    )
                )
                for contract_id in contract_rows.scalars():
                    send_contract_reminder.delay(contract_id, window)


async def _send_contract_reminder(contract_id: str, days_before: int) -> None:
    async with async_session_factory() as session:
        contract = await session.get(Contract, contract_id)
        if not contract:
            return

        account = await session.get(Account, contract.account_id)
        if not account:
            return
        account_status = (account.status or "").lower()
        if account_status not in REMINDER_ELIGIBLE_ACCOUNT_STATUSES:
            return

        if not contract.owner_email or not contract.owner_email.strip():
            return

        reminder_date = _today_for_timezone(account.timezone)
        already_sent = await session.scalar(
            select(ContractReminderLog.id).where(
                and_(
                    ContractReminderLog.contract_id == contract_id,
                    ContractReminderLog.days_before == days_before,
                    ContractReminderLog.reminder_date == reminder_date,
                )
            )
        )
        if already_sent:
            return

        subject = f"[knowrenewals] {contract.vendor_name} renewal notice"
        body = (
            f"Vendor: {contract.vendor_name}\n"
            f"Renewal: {contract.renewal_name or contract.contract_name or 'n/a'}\n"
            f"Type: {contract.renewal_type}\n"
            f"Renewal date: {contract.renewal_date}\n"
            f"Notice deadline: {contract.notice_deadline}\n"
            f"This is your {days_before}-day reminder."
        )
        await email_service.send_email(contract.owner_email, subject, body)

        log_entry = ContractReminderLog(
            contract_id=contract_id,
            days_before=days_before,
            reminder_date=reminder_date,
        )
        session.add(log_entry)
        try:
            await session.commit()
        except IntegrityError:
            # Another worker already logged this reminder window.
            await session.rollback()
