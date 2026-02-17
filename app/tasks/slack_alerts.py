from __future__ import annotations

import asyncio

from celery_app import celery_app
from app.db.session import async_session_factory
from app.services import slack as slack_service


@celery_app.task(name="app.tasks.slack_alerts.schedule_daily_slack_digests")
def schedule_daily_slack_digests() -> None:
    asyncio.run(_schedule_daily_slack_digests())


@celery_app.task(name="app.tasks.slack_alerts.reconcile_instant_slack_alerts")
def reconcile_instant_slack_alerts() -> None:
    asyncio.run(_reconcile_instant_slack_alerts())


@celery_app.task(name="app.tasks.slack_alerts.evaluate_contract_slack_alerts")
def evaluate_contract_slack_alerts(contract_id: str) -> None:
    asyncio.run(_evaluate_contract_slack_alerts(contract_id))


async def _schedule_daily_slack_digests() -> None:
    if not slack_service.is_enabled():
        return
    async with async_session_factory() as session:
        await slack_service.schedule_daily_digests(session)


async def _reconcile_instant_slack_alerts() -> None:
    if not slack_service.is_enabled():
        return
    async with async_session_factory() as session:
        await slack_service.reconcile_instant_alerts(session)


async def _evaluate_contract_slack_alerts(contract_id: str) -> None:
    if not slack_service.is_enabled():
        return
    async with async_session_factory() as session:
        await slack_service.evaluate_contract_alerts(session, contract_id)
