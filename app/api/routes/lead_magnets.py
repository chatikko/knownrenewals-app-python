from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, rate_limit_auth
from app.core.config import get_settings
from app.core.redis import get_redis_client
from app.db.models.lead_magnet import LeadMagnetDownload
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.common import CommonResponse, ListResponse
from app.schemas.lead_magnets import (
    LeadMagnetDownloadRead,
    LeadMagnetStatsResponse,
    LeadMagnetSubmitRequest,
    LeadMagnetSubmitResponse,
)
from app.services import lead_magnets

router = APIRouter(tags=["lead-magnets"])
settings = get_settings()


def _assert_enabled() -> None:
    if not settings.lead_magnet_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead magnet endpoint is disabled.")


@router.post(
    "/lead-magnets/renewal-template/submit",
    response_model=CommonResponse[LeadMagnetSubmitResponse],
    dependencies=[Depends(rate_limit_auth)],
)
@router.post(
    "/submit",
    response_model=CommonResponse[LeadMagnetSubmitResponse],
    dependencies=[Depends(rate_limit_auth)],
)
async def submit_renewal_template(
    payload: LeadMagnetSubmitRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis_client),
) -> CommonResponse[LeadMagnetSubmitResponse]:
    _assert_enabled()

    submission = await lead_magnets.submit_renewal_template(
        db,
        redis,
        email=payload.email,
        source_path=payload.source_path,
        utm_source=payload.utm_source,
        utm_medium=payload.utm_medium,
        utm_campaign=payload.utm_campaign,
        utm_term=payload.utm_term,
        utm_content=payload.utm_content,
        referrer=payload.referrer or request.headers.get("referer"),
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )

    data = LeadMagnetSubmitResponse(
        message=lead_magnets.GENERIC_SUBMIT_MESSAGE,
        status=submission.status,
    )
    return CommonResponse(data=data, status_code=status.HTTP_200_OK)


@router.get(
    "/admin/lead-magnets/renewal-template/stats",
    response_model=CommonResponse[LeadMagnetStatsResponse],
)
async def get_renewal_template_stats(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[LeadMagnetStatsResponse]:
    _assert_enabled()
    magnet_filter = LeadMagnetDownload.magnet_key == lead_magnets.MAGNET_KEY_RENEWAL_TEMPLATE

    total_submissions = await db.scalar(select(func.count()).select_from(LeadMagnetDownload).where(magnet_filter))
    successful_sends = await db.scalar(
        select(func.count()).select_from(LeadMagnetDownload).where(magnet_filter, LeadMagnetDownload.status == "sent")
    )
    failed_deliveries = await db.scalar(
        select(func.count()).select_from(LeadMagnetDownload).where(magnet_filter, LeadMagnetDownload.status == "failed")
    )
    skipped_submissions = await db.scalar(
        select(func.count()).select_from(LeadMagnetDownload).where(magnet_filter, LeadMagnetDownload.status == "skipped")
    )
    unique_emails = await db.scalar(
        select(func.count(func.distinct(LeadMagnetDownload.normalized_email))).where(magnet_filter)
    )

    data = LeadMagnetStatsResponse(
        total_submissions=total_submissions or 0,
        successful_sends=successful_sends or 0,
        unique_emails=unique_emails or 0,
        failed_deliveries=failed_deliveries or 0,
        skipped_submissions=skipped_submissions or 0,
    )
    return CommonResponse(data=data, status_code=status.HTTP_200_OK)


@router.get(
    "/admin/lead-magnets/renewal-template/downloads",
    response_model=ListResponse[LeadMagnetDownloadRead],
)
async def list_renewal_template_downloads(
    skip: int = 0,
    limit: int = 100,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[LeadMagnetDownloadRead]:
    _assert_enabled()
    magnet_filter = LeadMagnetDownload.magnet_key == lead_magnets.MAGNET_KEY_RENEWAL_TEMPLATE

    total = await db.scalar(select(func.count()).select_from(LeadMagnetDownload).where(magnet_filter))
    result = await db.execute(
        select(LeadMagnetDownload)
        .where(magnet_filter)
        .order_by(LeadMagnetDownload.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    items = list(result.scalars())
    return ListResponse(items=items, total=total or 0, status_code=status.HTTP_200_OK)


@router.get("/admin/lead-magnets/renewal-template/downloads.csv")
async def export_renewal_template_downloads_csv(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    _assert_enabled()
    magnet_filter = LeadMagnetDownload.magnet_key == lead_magnets.MAGNET_KEY_RENEWAL_TEMPLATE
    result = await db.execute(
        select(LeadMagnetDownload)
        .where(magnet_filter)
        .order_by(LeadMagnetDownload.created_at.desc())
    )
    items = list(result.scalars())

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "created_at",
            "email",
            "status",
            "sent_at",
            "failure_reason",
            "source_path",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
            "referrer",
        ]
    )
    for item in items:
        writer.writerow(
            [
                item.created_at.isoformat() if item.created_at else "",
                item.email,
                item.status,
                item.sent_at.isoformat() if item.sent_at else "",
                item.failure_reason or "",
                item.source_path or "",
                item.utm_source or "",
                item.utm_medium or "",
                item.utm_campaign or "",
                item.utm_term or "",
                item.utm_content or "",
                item.referrer or "",
            ]
        )

    filename = f"knowrenewals-renewal-template-leads-{datetime.now(timezone.utc).date().isoformat()}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
