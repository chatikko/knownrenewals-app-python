from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AccountAdminContext, get_current_account_admin
from app.core.config import get_settings
from app.core.redis import get_redis_client
from app.db.models.slack import SlackIntegration
from app.db.session import get_db
from app.schemas.common import CommonResponse, ListResponse
from app.schemas.integrations import (
    SlackChannelRead,
    SlackConfigUpdate,
    SlackInstallUrlResponse,
    SlackStatusResponse,
    SlackTestResponse,
)
from app.services import slack as slack_service

router = APIRouter(prefix="/integrations", tags=["integrations"])
settings = get_settings()


def _frontend_slack_path() -> str:
    return f"{settings.frontend_base_url.rstrip('/')}{settings.slack_post_connect_path}"


def _assert_enabled() -> None:
    if not settings.slack_integration_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slack integration is disabled.")


def _assert_account_eligible(account_id: str) -> None:
    if not slack_service.is_account_pilot_eligible(account_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slack integration is disabled.")


def _redirect_with_status(*, state: str, reason: str | None = None) -> RedirectResponse:
    base = _frontend_slack_path()
    query = f"?slack={state}"
    if reason:
        query = f"{query}&reason={quote_plus(reason)}"
    return RedirectResponse(url=f"{base}{query}", status_code=status.HTTP_302_FOUND)


async def _serialize_status(
    db: AsyncSession,
    context: AccountAdminContext,
    integration: SlackIntegration | None,
) -> SlackStatusResponse:
    plan_tier = str(context.account.plan_tier or "pro")
    entitlements = slack_service.resolve_slack_entitlements(plan_tier)

    if not integration:
        return SlackStatusResponse(
            slack_integration_enabled=settings.slack_integration_enabled,
            connected=False,
            plan_tier=plan_tier,
            instant_alerts_available=entitlements.instant_allowed,
            founders_digest_only=entitlements.founders_digest_only,
            timezone=context.account.timezone or "UTC",
            digest_hour_local=9,
            digest_enabled=entitlements.digest_allowed,
            instant_risk_enabled=False if not entitlements.instant_allowed else True,
            instant_due_7d_enabled=False if not entitlements.instant_allowed else True,
        )

    connected = bool(integration.is_active and integration.bot_access_token_encrypted)
    last_test = await slack_service.get_last_test_log(db, context.account.id)
    return SlackStatusResponse(
        slack_integration_enabled=settings.slack_integration_enabled,
        connected=connected,
        plan_tier=plan_tier,
        instant_alerts_available=entitlements.instant_allowed,
        founders_digest_only=entitlements.founders_digest_only,
        workspace_id=integration.workspace_id,
        workspace_name=integration.workspace_name,
        default_channel_id=integration.default_channel_id,
        default_channel_name=integration.default_channel_name,
        digest_enabled=integration.digest_enabled and entitlements.digest_allowed,
        instant_risk_enabled=integration.instant_risk_enabled and entitlements.instant_allowed,
        instant_due_7d_enabled=integration.instant_due_7d_enabled and entitlements.instant_allowed,
        digest_hour_local=integration.digest_hour_local,
        timezone=context.account.timezone or "UTC",
        is_degraded=integration.is_degraded,
        last_error_code=integration.last_error_code,
        last_error_message=integration.last_error_message,
        last_error_at=integration.last_error_at,
        last_test_success=last_test.success if last_test else None,
        last_test_sent_at=last_test.created_at if last_test else None,
    )


@router.get("/slack/install-url", response_model=CommonResponse[SlackInstallUrlResponse])
async def slack_install_url(
    context: AccountAdminContext = Depends(get_current_account_admin),
    redis: Redis = Depends(get_redis_client),
) -> CommonResponse[SlackInstallUrlResponse]:
    _assert_enabled()
    _assert_account_eligible(context.account.id)

    state = secrets.token_urlsafe(24)
    key = f"slack:oauth:state:{state}"
    value = json.dumps({"account_id": context.account.id, "user_id": context.user.id})
    await redis.set(key, value, ex=settings.slack_oauth_state_ttl_seconds)
    install_url = slack_service.build_install_url(state)
    return CommonResponse(data=SlackInstallUrlResponse(url=install_url), status_code=status.HTTP_200_OK)


@router.get("/slack/oauth/callback", include_in_schema=False)
async def slack_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    redis: Redis = Depends(get_redis_client),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    _assert_enabled()

    if error:
        return _redirect_with_status(state="error", reason=error)
    if not code or not state:
        return _redirect_with_status(state="error", reason="missing_code_or_state")

    state_key = f"slack:oauth:state:{state}"
    state_payload = await redis.get(state_key)
    await redis.delete(state_key)
    if not state_payload:
        return _redirect_with_status(state="error", reason="invalid_state")

    context = json.loads(state_payload)
    account_id = context.get("account_id")
    user_id = context.get("user_id")
    if not account_id or not user_id:
        return _redirect_with_status(state="error", reason="invalid_state_payload")
    if not slack_service.is_account_pilot_eligible(account_id):
        return _redirect_with_status(state="error", reason="not_eligible")

    try:
        oauth_payload = await slack_service.exchange_oauth_code(code)
        await slack_service.upsert_integration_from_oauth(
            db,
            account_id=account_id,
            connected_by_user_id=user_id,
            oauth_payload=oauth_payload,
        )
    except Exception as exc:
        return _redirect_with_status(state="error", reason=exc.__class__.__name__)

    return _redirect_with_status(state="connected")


@router.get("/slack/status", response_model=CommonResponse[SlackStatusResponse])
async def slack_status(
    context: AccountAdminContext = Depends(get_current_account_admin),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[SlackStatusResponse]:
    _assert_enabled()
    _assert_account_eligible(context.account.id)
    integration = await slack_service.get_integration(db, context.account.id)
    data = await _serialize_status(db, context, integration)
    return CommonResponse(data=data, status_code=status.HTTP_200_OK)


@router.get("/slack/channels", response_model=ListResponse[SlackChannelRead])
async def slack_channels(
    context: AccountAdminContext = Depends(get_current_account_admin),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[SlackChannelRead]:
    _assert_enabled()
    _assert_account_eligible(context.account.id)

    integration = await slack_service.get_active_integration(db, context.account.id)
    if not integration or not integration.bot_access_token_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connect Slack before loading channels.")

    token = slack_service.decrypt_bot_token(integration.bot_access_token_encrypted)
    channels = await slack_service.list_channels(token)
    items = [SlackChannelRead(id=channel.id, name=channel.name) for channel in channels]
    return ListResponse(items=items, total=len(items), status_code=status.HTTP_200_OK)


@router.put("/slack/config", response_model=CommonResponse[SlackStatusResponse])
async def slack_update_config(
    payload: SlackConfigUpdate,
    context: AccountAdminContext = Depends(get_current_account_admin),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[SlackStatusResponse]:
    _assert_enabled()
    _assert_account_eligible(context.account.id)

    integration = await slack_service.get_active_integration(db, context.account.id)
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slack integration is not connected.")

    entitlements = slack_service.resolve_slack_entitlements(context.account.plan_tier)

    integration.default_channel_id = payload.default_channel_id
    integration.default_channel_name = payload.default_channel_name
    integration.digest_enabled = payload.digest_enabled if entitlements.digest_allowed else False
    integration.instant_risk_enabled = payload.instant_risk_enabled if entitlements.instant_allowed else False
    integration.instant_due_7d_enabled = payload.instant_due_7d_enabled if entitlements.instant_allowed else False
    integration.digest_hour_local = payload.digest_hour_local

    await db.commit()
    await db.refresh(integration)

    data = await _serialize_status(db, context, integration)
    return CommonResponse(data=data, status_code=status.HTTP_200_OK)


@router.post("/slack/test", response_model=CommonResponse[SlackTestResponse])
async def slack_test_message(
    context: AccountAdminContext = Depends(get_current_account_admin),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[SlackTestResponse]:
    _assert_enabled()
    _assert_account_eligible(context.account.id)

    integration = await slack_service.get_active_integration(db, context.account.id)
    if not integration or not integration.default_channel_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select a default Slack channel first.")

    sent = await slack_service.send_account_alert(
        db,
        account_id=context.account.id,
        event_type="test",
        text=(
            ":white_check_mark: *Slack integration test from KnowRenewals*\n"
            "Alerts are connected. Daily digest is scheduled for 09:00 local account time."
        ),
    )
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Slack test message could not be sent. Please verify channel access and reconnect if needed.",
        )

    return CommonResponse(
        data=SlackTestResponse(message="Test message sent.", sent_at=datetime.now(timezone.utc)),
        status_code=status.HTTP_200_OK,
    )


@router.delete("/slack/disconnect", response_model=CommonResponse[dict[str, str]])
async def slack_disconnect(
    context: AccountAdminContext = Depends(get_current_account_admin),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[dict[str, str]]:
    _assert_enabled()
    _assert_account_eligible(context.account.id)

    integration = await slack_service.get_active_integration(db, context.account.id)
    if not integration:
        return CommonResponse(data={"message": "Slack integration already disconnected."}, status_code=status.HTTP_200_OK)

    if integration.bot_access_token_encrypted:
        try:
            await slack_service.revoke_token(slack_service.decrypt_bot_token(integration.bot_access_token_encrypted))
        except Exception:
            pass

    integration.is_active = False
    integration.bot_access_token_encrypted = None
    integration.bot_token_last4 = None
    integration.default_channel_id = None
    integration.default_channel_name = None
    integration.disconnected_at = datetime.now(timezone.utc)
    integration.last_error_code = None
    integration.last_error_message = None
    integration.last_error_at = None
    integration.is_degraded = False
    await db.commit()

    return CommonResponse(data={"message": "Slack integration disconnected."}, status_code=status.HTTP_200_OK)
