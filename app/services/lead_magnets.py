from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.lead_magnet import LeadMagnetDownload
from app.services.email import email_service

settings = get_settings()

MAGNET_KEY_RENEWAL_TEMPLATE = "renewal_template"
RENEWAL_TEMPLATE_FILENAME = "knowrenewals-renewal-tracking-template.xlsx"
RENEWAL_TEMPLATE_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
GENERIC_SUBMIT_MESSAGE = "Thank you. Check your inbox for the template."


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_ip_address(ip_address: str | None) -> str | None:
    if not ip_address:
        return None
    return hashlib.sha256(ip_address.encode("utf-8")).hexdigest()


def _clean(value: str | None, max_length: int) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:max_length]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _cooldown_key(normalized_email: str) -> str:
    return f"lead_magnet:{MAGNET_KEY_RENEWAL_TEMPLATE}:{normalized_email}"


def _template_path() -> Path:
    configured = Path(settings.lead_magnet_template_path)
    if configured.is_absolute():
        return configured
    cwd_candidate = Path.cwd() / configured
    if cwd_candidate.exists():
        return cwd_candidate
    backend_root = Path(__file__).resolve().parents[2]
    return backend_root / configured


def load_renewal_template_bytes() -> bytes:
    path = _template_path()
    if not path.exists():
        raise RuntimeError(f"Lead magnet template not found at {path}")
    return path.read_bytes()


async def submit_renewal_template(
    db: AsyncSession,
    redis: Redis,
    *,
    email: str,
    source_path: str | None = None,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
    utm_term: str | None = None,
    utm_content: str | None = None,
    referrer: str | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> LeadMagnetDownload:
    normalized_email = normalize_email(email)
    now = _utcnow()
    base_kwargs = {
        "magnet_key": MAGNET_KEY_RENEWAL_TEMPLATE,
        "email": email.strip(),
        "normalized_email": normalized_email,
        "source_path": _clean(source_path, 512),
        "utm_source": _clean(utm_source, 255),
        "utm_medium": _clean(utm_medium, 255),
        "utm_campaign": _clean(utm_campaign, 255),
        "utm_term": _clean(utm_term, 255),
        "utm_content": _clean(utm_content, 255),
        "referrer": _clean(referrer, 1024),
        "user_agent": _clean(user_agent, 1024),
        "ip_hash": hash_ip_address(ip_address),
    }

    cooldown_key = _cooldown_key(normalized_email)
    try:
        ttl = await redis.ttl(cooldown_key)
    except Exception:
        ttl = None
    if ttl and ttl > 0:
        skipped = LeadMagnetDownload(
            **base_kwargs,
            status="skipped",
            failure_reason=f"cooldown_active:{ttl}s",
        )
        db.add(skipped)
        await db.commit()
        await db.refresh(skipped)
        return skipped

    submission = LeadMagnetDownload(
        **base_kwargs,
        status="pending",
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    try:
        template_bytes = load_renewal_template_bytes()
        subject = "Your free renewal tracking spreadsheet template"
        body = (
            "Here is your free KnowRenewals renewal tracking spreadsheet template.\n\n"
            "It includes formula-ready columns for subscription, contract, SaaS, domain, and license renewals.\n\n"
            "When your process outgrows spreadsheets, start your free trial at https://knowrenewals.com/signup.\n"
        )
        await email_service.send_email_with_attachment(
            to_email=submission.email,
            subject=subject,
            body=body,
            filename=RENEWAL_TEMPLATE_FILENAME,
            content_bytes=template_bytes,
            mime_type=RENEWAL_TEMPLATE_MIME_TYPE,
        )
    except Exception as exc:
        submission.status = "failed"
        submission.failure_reason = f"{exc.__class__.__name__}: {str(exc)}"[:1000]
        await db.commit()
        await db.refresh(submission)
        return submission

    submission.status = "sent"
    submission.sent_at = now
    submission.failure_reason = None
    await db.commit()
    await db.refresh(submission)
    try:
        await redis.set(cooldown_key, "1", ex=settings.lead_magnet_resend_cooldown_seconds)
    except Exception:
        pass
    return submission
