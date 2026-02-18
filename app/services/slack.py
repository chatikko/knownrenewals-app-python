from __future__ import annotations

import asyncio
import base64
import hashlib
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.account import Account
from app.db.models.contract import Contract
from app.db.models.slack import SlackAlertState, SlackDeliveryLog, SlackIntegration

settings = get_settings()


class SlackApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.retryable = retryable


@dataclass
class SlackChannel:
    id: str
    name: str


@dataclass(frozen=True)
class SlackEntitlements:
    digest_allowed: bool
    instant_allowed: bool
    founders_digest_only: bool


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def is_enabled() -> bool:
    return settings.slack_integration_enabled


def is_account_pilot_eligible(account_id: str) -> bool:
    allowlist = settings.slack_pilot_account_ids_list
    if not allowlist:
        return True
    return account_id in allowlist


def resolve_slack_entitlements(plan_tier: str | None) -> SlackEntitlements:
    normalized = (plan_tier or "").strip().lower()
    if normalized == "founders":
        return SlackEntitlements(digest_allowed=True, instant_allowed=False, founders_digest_only=True)
    return SlackEntitlements(digest_allowed=True, instant_allowed=True, founders_digest_only=False)


def _resolve_fernet() -> Fernet:
    if settings.slack_token_encryption_key:
        key_bytes = settings.slack_token_encryption_key.encode("utf-8")
    else:
        digest = hashlib.sha256(settings.jwt_secret.encode("utf-8")).digest()
        key_bytes = base64.urlsafe_b64encode(digest)
    return Fernet(key_bytes)


def encrypt_bot_token(token: str) -> str:
    return _resolve_fernet().encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_bot_token(token_encrypted: str) -> str:
    return _resolve_fernet().decrypt(token_encrypted.encode("utf-8")).decode("utf-8")


def build_install_url(state: str) -> str:
    if not settings.slack_client_id or not settings.slack_oauth_redirect_uri:
        raise RuntimeError("Slack OAuth is not configured. Missing SLACK_CLIENT_ID or SLACK_OAUTH_REDIRECT_URI.")

    query = urlencode(
        {
            "client_id": settings.slack_client_id,
            "scope": settings.slack_bot_scopes,
            "state": state,
            "redirect_uri": settings.slack_oauth_redirect_uri,
        }
    )
    return f"https://slack.com/oauth/v2/authorize?{query}"


async def exchange_oauth_code(code: str) -> dict[str, Any]:
    if not settings.slack_client_id or not settings.slack_client_secret or not settings.slack_oauth_redirect_uri:
        raise RuntimeError(
            "Slack OAuth is not configured. Missing one of SLACK_CLIENT_ID, SLACK_CLIENT_SECRET, SLACK_OAUTH_REDIRECT_URI."
        )

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "code": code,
                "client_id": settings.slack_client_id,
                "client_secret": settings.slack_client_secret,
                "redirect_uri": settings.slack_oauth_redirect_uri,
            },
        )

    if response.status_code >= 500:
        raise SlackApiError("Slack OAuth is temporarily unavailable.", status_code=response.status_code, retryable=True)
    if response.status_code >= 400:
        raise SlackApiError("Slack OAuth failed.", status_code=response.status_code)

    payload = response.json()
    if not payload.get("ok"):
        error_code = str(payload.get("error") or "oauth_failed")
        raise SlackApiError("Slack OAuth failed.", error_code=error_code)
    return payload


async def revoke_token(token: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            "https://slack.com/api/auth.revoke",
            headers={"Authorization": f"Bearer {token}"},
            data={"test": "false"},
        )


async def _post_slack_api(token: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    url = f"https://slack.com/api/{endpoint}"

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, json=payload, headers=headers)

    retryable = response.status_code == 429 or response.status_code >= 500
    if response.status_code >= 400:
        raise SlackApiError("Slack API request failed.", status_code=response.status_code, retryable=retryable)

    data = response.json()
    if not data.get("ok"):
        error_code = str(data.get("error") or "slack_api_error")
        retryable_errors = {"ratelimited", "internal_error", "fatal_error", "service_unavailable"}
        raise SlackApiError(
            "Slack API request failed.",
            status_code=response.status_code,
            error_code=error_code,
            retryable=error_code in retryable_errors,
        )
    return data


async def _get_slack_api(token: str, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://slack.com/api/{endpoint}"

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, params=params, headers=headers)

    retryable = response.status_code == 429 or response.status_code >= 500
    if response.status_code >= 400:
        raise SlackApiError("Slack API request failed.", status_code=response.status_code, retryable=retryable)

    data = response.json()
    if not data.get("ok"):
        error_code = str(data.get("error") or "slack_api_error")
        retryable_errors = {"ratelimited", "internal_error", "fatal_error", "service_unavailable"}
        raise SlackApiError(
            "Slack API request failed.",
            status_code=response.status_code,
            error_code=error_code,
            retryable=error_code in retryable_errors,
        )
    return data


async def list_channels(token: str) -> list[SlackChannel]:
    channels: list[SlackChannel] = []
    cursor = ""
    while True:
        payload: dict[str, Any] = {
            "types": "public_channel,private_channel",
            "exclude_archived": True,
            "limit": 200,
        }
        if cursor:
            payload["cursor"] = cursor
        data = await _get_slack_api(token, "conversations.list", payload)
        for channel in data.get("channels", []):
            channel_id = channel.get("id")
            name = channel.get("name")
            if channel_id and name:
                channels.append(SlackChannel(id=channel_id, name=name))
        cursor = data.get("response_metadata", {}).get("next_cursor") or ""
        if not cursor:
            break
    channels.sort(key=lambda item: item.name.lower())
    return channels


def _normalize_channel_name(name: str) -> str:
    normalized = "".join(ch for ch in name.lower() if ch.isalnum() or ch in {"-", "_"}).strip("-_")
    if not normalized:
        return "knowrenewal"
    return normalized[:80]


def _sanitize_incoming_channel_name(name: str | None) -> str | None:
    if not name:
        return None
    normalized = name.strip()
    if not normalized:
        return None
    return normalized[1:] if normalized.startswith("#") else normalized


async def _find_channel_by_name(token: str, channel_name: str) -> SlackChannel | None:
    target = _normalize_channel_name(channel_name)
    channels = await list_channels(token)
    for channel in channels:
        if channel.name.lower() == target:
            return channel
    return None


async def get_or_create_channel(token: str, channel_name: str) -> SlackChannel | None:
    normalized_name = _normalize_channel_name(channel_name)
    try:
        data = await _post_slack_api(
            token,
            "conversations.create",
            {
                "name": normalized_name,
                "is_private": False,
            },
        )
        channel_data = data.get("channel") or {}
        channel_id = channel_data.get("id")
        created_name = channel_data.get("name")
        if channel_id and created_name:
            return SlackChannel(id=channel_id, name=created_name)
    except SlackApiError as exc:
        if exc.error_code in {"name_taken", "already_exists"}:
            return await _find_channel_by_name(token, normalized_name)
        if exc.error_code in {"missing_scope", "restricted_action", "not_allowed_token_type"}:
            return None
        raise

    return await _find_channel_by_name(token, normalized_name)


async def post_message(
    token: str,
    channel_id: str,
    text: str,
    *,
    blocks: list[dict[str, Any]] | None = None,
) -> str:
    last_error: SlackApiError | None = None
    for attempt in range(settings.slack_max_retries + 1):
        try:
            payload: dict[str, Any] = {
                "channel": channel_id,
                "text": text,
                "unfurl_links": False,
                "unfurl_media": False,
            }
            if blocks:
                payload["blocks"] = blocks
            data = await _post_slack_api(token, "chat.postMessage", payload)
            return str(data.get("ts") or "")
        except SlackApiError as exc:
            last_error = exc
            if attempt >= settings.slack_max_retries or not exc.retryable:
                break
            delay = settings.slack_base_backoff_seconds * (2**attempt) + random.uniform(0, 0.25)
            await asyncio.sleep(delay)

    if last_error:
        raise last_error
    raise SlackApiError("Slack message send failed.")


async def get_active_integration(db: AsyncSession, account_id: str) -> SlackIntegration | None:
    return await db.scalar(
        select(SlackIntegration).where(SlackIntegration.account_id == account_id, SlackIntegration.is_active.is_(True))
    )


async def get_integration(db: AsyncSession, account_id: str) -> SlackIntegration | None:
    return await db.scalar(select(SlackIntegration).where(SlackIntegration.account_id == account_id))


async def upsert_integration_from_oauth(
    db: AsyncSession,
    *,
    account_id: str,
    connected_by_user_id: str,
    oauth_payload: dict[str, Any],
) -> SlackIntegration:
    access_token = oauth_payload.get("access_token")
    if not access_token:
        raise SlackApiError("Slack OAuth payload did not include an access token.")
    access_token_str = str(access_token)

    team = oauth_payload.get("team") or {}
    workspace_id = str(team.get("id") or "")
    workspace_name = str(team.get("name") or "Slack Workspace")
    if not workspace_id:
        raise SlackApiError("Slack OAuth payload did not include workspace information.")

    integration = await get_active_integration(db, account_id)
    if not integration:
        integration = await db.scalar(select(SlackIntegration).where(SlackIntegration.account_id == account_id))
        if not integration:
            integration = SlackIntegration(account_id=account_id, workspace_id=workspace_id, workspace_name=workspace_name)
            db.add(integration)

    incoming_webhook = oauth_payload.get("incoming_webhook") or {}

    integration.workspace_id = workspace_id
    integration.workspace_name = workspace_name
    integration.bot_user_id = oauth_payload.get("bot_user_id")
    integration.bot_access_token_encrypted = encrypt_bot_token(access_token_str)
    integration.bot_token_last4 = access_token_str[-4:]
    integration.default_channel_id = incoming_webhook.get("channel_id") or integration.default_channel_id
    integration.default_channel_name = (
        _sanitize_incoming_channel_name(incoming_webhook.get("channel")) or integration.default_channel_name
    )

    channel_warning: tuple[str, str] | None = None
    if not integration.default_channel_id:
        try:
            auto_channel = await get_or_create_channel(access_token_str, "knowrenewal")
            if auto_channel:
                integration.default_channel_id = auto_channel.id
                integration.default_channel_name = auto_channel.name
            else:
                channel_warning = (
                    "default_channel_setup_failed",
                    "Could not auto-create #knowrenewal. Add channels:manage scope and reinstall app, or choose a channel manually.",
                )
        except SlackApiError as exc:
            channel_warning = (
                exc.error_code or "default_channel_setup_failed",
                f"Could not auto-create #knowrenewal. Slack error: {exc.error_code or 'unknown'}.",
            )

    integration.is_active = True
    integration.is_degraded = False
    integration.last_error_code = None
    integration.last_error_message = None
    integration.last_error_at = None
    if channel_warning:
        integration.last_error_code = channel_warning[0]
        integration.last_error_message = channel_warning[1]
        integration.last_error_at = _now_utc()
    integration.connected_by_user_id = connected_by_user_id
    integration.connected_at = _now_utc()
    integration.disconnected_at = None

    await db.commit()
    await db.refresh(integration)
    return integration


async def get_last_test_log(db: AsyncSession, account_id: str) -> SlackDeliveryLog | None:
    result = await db.execute(
        select(SlackDeliveryLog)
        .where(SlackDeliveryLog.account_id == account_id, SlackDeliveryLog.event_type == "test")
        .order_by(desc(SlackDeliveryLog.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _existing_alert_state(
    db: AsyncSession,
    *,
    account_id: str,
    contract_id: str | None,
    event_type: str,
    event_date_key: str,
) -> SlackAlertState | None:
    query = select(SlackAlertState).where(
        SlackAlertState.account_id == account_id,
        SlackAlertState.event_type == event_type,
        SlackAlertState.event_date_key == event_date_key,
    )
    if contract_id:
        query = query.where(SlackAlertState.contract_id == contract_id)
    else:
        query = query.where(SlackAlertState.contract_id.is_(None))
    return await db.scalar(query)


async def _update_degraded_state(db: AsyncSession, integration: SlackIntegration, *, success: bool, error_code: str | None, error_message: str | None) -> None:
    if success:
        integration.is_degraded = False
        integration.last_error_code = None
        integration.last_error_message = None
        integration.last_error_at = None
        return

    integration.last_error_code = error_code
    integration.last_error_message = error_message
    integration.last_error_at = _now_utc()

    result = await db.execute(
        select(SlackDeliveryLog.success)
        .where(SlackDeliveryLog.account_id == integration.account_id)
        .order_by(desc(SlackDeliveryLog.created_at))
        .limit(3)
    )
    recent = [row[0] for row in result.all()]
    integration.is_degraded = len(recent) >= 3 and all(not item for item in recent)


def _is_auth_token_error(error: SlackApiError) -> bool:
    auth_error_codes = {
        "invalid_auth",
        "account_inactive",
        "token_revoked",
        "not_authed",
    }
    if error.error_code and error.error_code in auth_error_codes:
        return True
    if error.status_code and error.status_code in {401, 403}:
        return True
    return False


def _is_channel_config_error(error: SlackApiError) -> bool:
    channel_error_codes = {
        "channel_not_found",
        "not_in_channel",
        "is_archived",
    }
    return bool(error.error_code and error.error_code in channel_error_codes)


async def send_account_alert(
    db: AsyncSession,
    *,
    account_id: str,
    event_type: str,
    text: str,
    contract_id: str | None = None,
    event_date_key: str | None = None,
    plan_tier: str | None = None,
    blocks: list[dict[str, Any]] | None = None,
) -> bool:
    if not is_account_pilot_eligible(account_id):
        return False

    if event_type in {"risk", "due_7d", "daily_digest"}:
        effective_plan_tier = plan_tier
        if effective_plan_tier is None:
            account = await db.get(Account, account_id)
            effective_plan_tier = account.plan_tier if account else None
        entitlements = resolve_slack_entitlements(effective_plan_tier)
        if event_type in {"risk", "due_7d"} and not entitlements.instant_allowed:
            return False
        if event_type == "daily_digest" and not entitlements.digest_allowed:
            return False

    integration = await get_active_integration(db, account_id)
    if not integration or not integration.bot_access_token_encrypted or not integration.default_channel_id:
        return False

    if event_date_key:
        existing = await _existing_alert_state(
            db,
            account_id=account_id,
            contract_id=contract_id,
            event_type=event_type,
            event_date_key=event_date_key,
        )
        if existing:
            return False

    try:
        message_ts = await post_message(
            decrypt_bot_token(integration.bot_access_token_encrypted),
            integration.default_channel_id,
            text,
            blocks=blocks,
        )
    except SlackApiError as exc:
        error_message = str(exc)
        if exc.error_code:
            error_message = f"{error_message} (code={exc.error_code})"

        log = SlackDeliveryLog(
            account_id=account_id,
            contract_id=contract_id,
            event_type=event_type,
            success=False,
            http_status=exc.status_code,
            error_code=exc.error_code,
            error_message=error_message,
        )
        db.add(log)
        if _is_auth_token_error(exc):
            integration.is_active = False
            integration.is_degraded = True
            integration.last_error_code = exc.error_code or "delivery_disabled"
            integration.last_error_message = error_message
            integration.last_error_at = _now_utc()
            integration.disconnected_at = _now_utc()
            integration.bot_access_token_encrypted = None
            integration.bot_token_last4 = None
        elif _is_channel_config_error(exc):
            integration.is_active = True
            integration.is_degraded = True
            integration.last_error_code = exc.error_code or "channel_reconfiguration_required"
            integration.last_error_message = error_message
            integration.last_error_at = _now_utc()
            integration.default_channel_id = None
            integration.default_channel_name = None
            integration.disconnected_at = None
        else:
            await _update_degraded_state(
                db,
                integration,
                success=False,
                error_code=exc.error_code,
                error_message=error_message,
            )
        await db.commit()
        return False

    if event_date_key:
        db.add(
            SlackAlertState(
                account_id=account_id,
                contract_id=contract_id,
                event_type=event_type,
                event_date_key=event_date_key,
                sent_at=_now_utc(),
                message_ts=message_ts or None,
            )
        )

    db.add(
        SlackDeliveryLog(
            account_id=account_id,
            contract_id=contract_id,
            event_type=event_type,
            success=True,
            http_status=200,
        )
    )
    await _update_degraded_state(db, integration, success=True, error_code=None, error_message=None)
    await db.commit()
    return True


def _frontend_contract_url(contract_id: str) -> str:
    return f"{settings.frontend_base_url.rstrip('/')}/contracts/{contract_id}"


def _derive_risk(contract: Contract, today: date) -> bool:
    return (contract.notice_deadline - today).days <= 7


def _display_name(contract: Contract) -> str:
    return contract.renewal_name or contract.contract_name or "n/a"


def _format_date(value: date) -> str:
    return value.strftime("%b %d, %Y")


def _format_relative_days(days: int) -> str:
    if days > 0:
        return f"{days} days"
    if days == 0:
        return "Today"
    return f"Overdue by {abs(days)} days"


def _build_risk_alert_message(contract: Contract, today: date) -> tuple[str, list[dict[str, Any]]]:
    contract_url = _frontend_contract_url(contract.id)
    days_to_notice = (contract.notice_deadline - today).days
    summary = "Immediate review is recommended."
    if days_to_notice > 0:
        summary = f"Notice deadline is in {days_to_notice} day(s). Prepare renewal decision now."
    elif days_to_notice == 0:
        summary = "Notice deadline is today. Immediate action is required."
    else:
        summary = f"Notice deadline passed {abs(days_to_notice)} day(s) ago. Escalate immediately."

    text = (
        f"Risk renewal alert: {contract.vendor_name} - {_display_name(contract)}. "
        f"Notice deadline {_format_date(contract.notice_deadline)}. {summary}"
    )
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Risk Renewal Alert"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Vendor*\n{contract.vendor_name}"},
                {"type": "mrkdwn", "text": f"*Renewal*\n{_display_name(contract)}"},
                {"type": "mrkdwn", "text": f"*Notice Deadline*\n{_format_date(contract.notice_deadline)}"},
                {"type": "mrkdwn", "text": f"*Time to Notice*\n{_format_relative_days(days_to_notice)}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Action Required*\n{summary}"},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "style": "danger",
                    "text": {"type": "plain_text", "text": "Open Contract"},
                    "url": contract_url,
                }
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "KnowRenewals automated alert"}],
        },
    ]
    return text, blocks


def _build_due_soon_alert_message(contract: Contract, today: date) -> tuple[str, list[dict[str, Any]]]:
    contract_url = _frontend_contract_url(contract.id)
    days_to_renewal = (contract.renewal_date - today).days
    summary = f"Renewal is due in {days_to_renewal} day(s). Confirm owner action."
    if days_to_renewal == 0:
        summary = "Renewal is due today. Confirm action and approval immediately."

    text = (
        f"Renewal due within 7 days: {contract.vendor_name} - {_display_name(contract)}. "
        f"Renewal date {_format_date(contract.renewal_date)}. {summary}"
    )
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Renewal Due Within 7 Days"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Vendor*\n{contract.vendor_name}"},
                {"type": "mrkdwn", "text": f"*Renewal*\n{_display_name(contract)}"},
                {"type": "mrkdwn", "text": f"*Renewal Date*\n{_format_date(contract.renewal_date)}"},
                {"type": "mrkdwn", "text": f"*Time to Renewal*\n{_format_relative_days(days_to_renewal)}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Recommended Action*\n{summary}"},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "style": "primary",
                    "text": {"type": "plain_text", "text": "Open Contract"},
                    "url": contract_url,
                }
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "KnowRenewals automated alert"}],
        },
    ]
    return text, blocks


async def evaluate_contract_alerts(db: AsyncSession, contract_id: str) -> None:
    contract = await db.get(Contract, contract_id)
    if not contract:
        return

    account = await db.get(Account, contract.account_id)
    if not account:
        return

    if not is_account_pilot_eligible(account.id):
        return

    entitlements = resolve_slack_entitlements(account.plan_tier)
    if not entitlements.instant_allowed:
        return

    integration = await get_active_integration(db, contract.account_id)
    if not integration:
        return

    today = date.today()
    risk_now = _derive_risk(contract, today)
    renewal_days = (contract.renewal_date - today).days
    due_soon_now = 0 <= renewal_days <= 7

    if integration.instant_risk_enabled and risk_now:
        risk_text, risk_blocks = _build_risk_alert_message(contract, today)
        await send_account_alert(
            db,
            account_id=contract.account_id,
            contract_id=contract.id,
            event_type="risk",
            event_date_key=contract.notice_deadline.isoformat(),
            plan_tier=account.plan_tier,
            text=risk_text,
            blocks=risk_blocks,
        )

    if integration.instant_due_7d_enabled and due_soon_now:
        due_text, due_blocks = _build_due_soon_alert_message(contract, today)
        await send_account_alert(
            db,
            account_id=contract.account_id,
            contract_id=contract.id,
            event_type="due_7d",
            event_date_key=contract.renewal_date.isoformat(),
            plan_tier=account.plan_tier,
            text=due_text,
            blocks=due_blocks,
        )


async def reconcile_instant_alerts(db: AsyncSession) -> None:
    result = await db.execute(select(Contract.id))
    for contract_id in result.scalars():
        await evaluate_contract_alerts(db, contract_id)


def _resolve_tz(name: str | None) -> ZoneInfo:
    if not name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


DIGEST_SECTION_ITEM_LIMIT = 6
DIGEST_SECTION_MAX_CHARS = 2600


def _truncate_text(value: str, max_chars: int, *, suffix: str = "...") -> str:
    if len(value) <= max_chars:
        return value
    cut_at = max_chars - len(suffix)
    if cut_at <= 0:
        return suffix[:max_chars]
    return value[:cut_at].rstrip() + suffix


def _owner_or_unassigned(contract: Contract) -> str:
    owner = (contract.owner_email or "").strip()
    return owner if owner else "Unassigned"


def _frontend_contracts_url() -> str:
    return f"{settings.frontend_base_url.rstrip('/')}/contracts"


def _digest_item_line(contract: Contract, *, date_label: str, date_value: date) -> str:
    return (
        f"- *Vendor:* {contract.vendor_name} | "
        f"*Renewal:* {_display_name(contract)} | "
        f"*{date_label}:* {_format_date(date_value)} | "
        f"*Owner:* {_owner_or_unassigned(contract)} | "
        f"<{_frontend_contract_url(contract.id)}|Open>"
    )


def _build_digest_section_block(
    title: str,
    items: list[Contract],
    *,
    date_label: str,
    date_resolver: Callable[[Contract], date],
    max_items: int = DIGEST_SECTION_ITEM_LIMIT,
    max_chars: int = DIGEST_SECTION_MAX_CHARS,
) -> dict[str, Any]:
    lines = [f"*{title}* ({len(items)})"]
    if not items:
        lines.append("- none")
    else:
        shown = items[:max_items]
        lines.extend(_digest_item_line(item, date_label=date_label, date_value=date_resolver(item)) for item in shown)
        if len(items) > max_items:
            lines.append(f"- ...and {len(items) - max_items} more")

    section_text = _truncate_text("\n".join(lines), max_chars)
    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": section_text,
        },
    }


async def _daily_digest_payload(
    db: AsyncSession,
    account_id: str,
    today_local: date,
    timezone_name: str,
) -> tuple[str, list[dict[str, Any]]] | None:
    result = await db.execute(
        select(Contract).where(Contract.account_id == account_id).order_by(Contract.renewal_date.asc())
    )
    contracts = list(result.scalars())
    if not contracts:
        return None

    due_30_all = [item for item in contracts if 0 <= (item.renewal_date - today_local).days <= 30]
    due_7 = [item for item in due_30_all if 0 <= (item.renewal_date - today_local).days <= 7]
    due_30 = [item for item in due_30_all if 8 <= (item.renewal_date - today_local).days <= 30]
    risk_items = [item for item in contracts if _derive_risk(item, today_local)]

    # Keep prior gating behavior: if nothing is within 30 days and no risk, do not send.
    if not due_30_all and not risk_items:
        return None

    header_date = _format_date(today_local)
    summary_line = f"Risk: {len(risk_items)} | Due in 7 days: {len(due_7)} | Due in 30 days: {len(due_30)}"

    text = (
        f"KnowRenewals daily digest ({header_date}, {timezone_name}). "
        f"{summary_line}. Review renewals: {_frontend_contracts_url()}"
    )
    text = _truncate_text(text, 500)

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "KnowRenewals Daily Digest"},
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"*Date:* {header_date}"},
                {"type": "mrkdwn", "text": f"*Timezone:* {timezone_name}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Summary*\n{summary_line}"},
        },
        {"type": "divider"},
        _build_digest_section_block(
            "Risk renewals",
            risk_items,
            date_label="Notice Deadline",
            date_resolver=lambda item: item.notice_deadline,
        ),
        _build_digest_section_block(
            "Due in 7 days",
            due_7,
            date_label="Renewal Date",
            date_resolver=lambda item: item.renewal_date,
        ),
        _build_digest_section_block(
            "Due in 30 days",
            due_30,
            date_label="Renewal Date",
            date_resolver=lambda item: item.renewal_date,
        ),
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "style": "primary",
                    "text": {"type": "plain_text", "text": "Review Renewals"},
                    "url": _frontend_contracts_url(),
                }
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "KnowRenewals automated digest"}],
        },
    ]
    return text, blocks


async def schedule_daily_digests(db: AsyncSession) -> None:
    now_utc = _now_utc()
    integrations = await db.execute(
        select(SlackIntegration).where(
            SlackIntegration.is_active.is_(True),
            SlackIntegration.digest_enabled.is_(True),
        )
    )
    for integration in integrations.scalars():
        account = await db.get(Account, integration.account_id)
        if not account:
            continue

        if not is_account_pilot_eligible(account.id):
            continue

        entitlements = resolve_slack_entitlements(account.plan_tier)
        if not entitlements.digest_allowed:
            continue

        local_now = now_utc.astimezone(_resolve_tz(account.timezone))
        if local_now.hour != integration.digest_hour_local:
            continue

        timezone_name = account.timezone or "UTC"
        daily_payload = await _daily_digest_payload(db, account.id, local_now.date(), timezone_name)
        if not daily_payload:
            continue
        daily_text, daily_blocks = daily_payload

        await send_account_alert(
            db,
            account_id=account.id,
            event_type="daily_digest",
            event_date_key=local_now.date().isoformat(),
            plan_tier=account.plan_tier,
            text=daily_text,
            blocks=daily_blocks,
        )
