from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import delete

from app.db.models.refresh_token import RefreshToken
from app.db.session import async_session_factory
from celery_app import celery_app


@celery_app.task(name="app.tasks.cleanup.purge_expired_refresh_tokens")
def purge_expired_refresh_tokens() -> None:
    asyncio.run(_purge_expired_refresh_tokens())


async def _purge_expired_refresh_tokens() -> None:
    async with async_session_factory() as session:
        now = datetime.now(timezone.utc)
        await session.execute(delete(RefreshToken).where(RefreshToken.expires_at < now))
        await session.commit()
