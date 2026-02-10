from __future__ import annotations

import asyncio
from datetime import date, timedelta

from sqlalchemy import and_, select

from app.db.models.contract import Contract, ContractReminderLog
from app.db.session import async_session_factory
from app.services.email import email_service
from celery_app import celery_app

REMINDER_WINDOWS = (30, 14, 7)


@celery_app.task(name="app.tasks.reminders.schedule_notice_reminders")
def schedule_notice_reminders() -> None:
    asyncio.run(_schedule_notice_reminders())


@celery_app.task(name="app.tasks.reminders.send_contract_reminder")
def send_contract_reminder(contract_id: str, days_before: int) -> None:
    asyncio.run(_send_contract_reminder(contract_id, days_before))


async def _schedule_notice_reminders() -> None:
    async with async_session_factory() as session:
        today = date.today()
        for window in REMINDER_WINDOWS:
            target_date = today + timedelta(days=window)
            result = await session.execute(select(Contract).where(Contract.notice_deadline == target_date))
            for contract in result.scalars():
                send_contract_reminder.delay(contract.id, window)


async def _send_contract_reminder(contract_id: str, days_before: int) -> None:
    async with async_session_factory() as session:
        contract = await session.get(Contract, contract_id)
        if not contract:
            return

        already_sent = await session.scalar(
            select(ContractReminderLog).where(
                and_(
                    ContractReminderLog.contract_id == contract_id,
                    ContractReminderLog.days_before == days_before,
                    ContractReminderLog.reminder_date == date.today(),
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
            reminder_date=date.today(),
        )
        session.add(log_entry)
        await session.commit()
