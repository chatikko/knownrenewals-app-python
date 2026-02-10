from fastapi import APIRouter, Depends, Header, Request, status
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.account import Account
from app.db.models.billing import BillingEvent
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.billing import BillingActionResponse, BillingStatusResponse, CheckoutSessionRequest, CheckoutSessionResponse
from app.schemas.common import CommonResponse
from app.services.account_limits import normalize_plan_tier
from app.services.stripe import stripe_service

router = APIRouter(prefix="/billing", tags=["billing"])
logger = structlog.get_logger(__name__)
SUPPORTED_WEBHOOK_EVENTS = {
    "checkout.session.completed",
    "invoice.paid",
    "invoice.payment_failed",
    "customer.subscription.deleted",
}


@router.get("/status", response_model=CommonResponse[BillingStatusResponse])
async def billing_status(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> CommonResponse[BillingStatusResponse]:
    account = await db.get(Account, current_user.account_id)
    cancel_at_period_end = False
    if account and account.stripe_subscription_id:
        try:
            subscription = stripe_service.get_subscription(account.stripe_subscription_id)
            cancel_at_period_end = bool(getattr(subscription, "cancel_at_period_end", False))
        except Exception as exc:
            logger.warning(
                "billing.status.subscription_lookup_failed",
                account_id=getattr(account, "id", None),
                subscription_id=account.stripe_subscription_id,
                error=str(exc),
            )

    founders_count = await db.scalar(select(func.count()).select_from(Account).where(Account.plan_tier == "founders"))
    founders_limit = 50
    founders_slots_remaining = max(0, founders_limit - int(founders_count or 0))
    founders_available = founders_slots_remaining > 0

    data = BillingStatusResponse(
        plan_tier=getattr(account, "plan_tier", None),
        plan=account.plan,
        status=account.status,
        cancel_at_period_end=cancel_at_period_end,
        founders_available=founders_available,
        founders_slots_remaining=founders_slots_remaining,
        stripe_customer_id=account.stripe_customer_id,
        stripe_subscription_id=account.stripe_subscription_id,
    )
    return CommonResponse(data=data, status_code=status.HTTP_200_OK)


@router.post("/checkout-session", response_model=CommonResponse[CheckoutSessionResponse])
async def create_checkout_session(
    payload: CheckoutSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[CheckoutSessionResponse]:
    account = await db.get(Account, current_user.account_id)
    session = stripe_service.create_checkout_session(
        account_id=account.id,
        plan=payload.plan,
        success_url=str(payload.success_url),
        cancel_url=str(payload.cancel_url),
        customer_id=account.stripe_customer_id,
    )
    return CommonResponse(data=CheckoutSessionResponse(url=session.url), status_code=status.HTTP_200_OK)


@router.post("/cancel", response_model=CommonResponse[BillingActionResponse])
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[BillingActionResponse]:
    account = await db.get(Account, current_user.account_id)
    if not account or not account.stripe_subscription_id:
        return CommonResponse(
            data=BillingActionResponse(message="No active Stripe subscription found."),
            status_code=status.HTTP_200_OK,
        )

    stripe_service.set_cancel_at_period_end(account.stripe_subscription_id, True)
    return CommonResponse(
        data=BillingActionResponse(message="Subscription will cancel at period end."),
        status_code=status.HTTP_200_OK,
    )


@router.post("/resume", response_model=CommonResponse[BillingActionResponse])
async def resume_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[BillingActionResponse]:
    account = await db.get(Account, current_user.account_id)
    if not account or not account.stripe_subscription_id:
        return CommonResponse(
            data=BillingActionResponse(message="No active Stripe subscription found."),
            status_code=status.HTTP_200_OK,
        )

    stripe_service.set_cancel_at_period_end(account.stripe_subscription_id, False)
    return CommonResponse(
        data=BillingActionResponse(message="Subscription resumed."),
        status_code=status.HTTP_200_OK,
    )


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
):
    payload = await request.body()
    event = stripe_service.parse_event(payload, stripe_signature)
    event_type = event["type"]

    if event_type not in SUPPORTED_WEBHOOK_EVENTS:
        return {"status": "ignored"}

    event_id = event["id"]
    already_processed = await db.scalar(select(BillingEvent).where(BillingEvent.stripe_event_id == event_id))
    if already_processed:
        return {"status": "duplicate"}

    account = await _handle_event(event, db)
    db.add(
        BillingEvent(
            account_id=account.id if account else None,
            stripe_event_id=event_id,
            event_type=event_type,
            status="processed" if account else "unmatched",
        )
    )
    await db.commit()
    return {"status": "ok"}


async def _handle_event(event: dict, db: AsyncSession) -> Account | None:
    event_type = event["type"]
    data = event["data"]["object"]

    account = await _resolve_account(data, db)

    if event_type == "checkout.session.completed" and account:
        subscription_id = data.get("subscription")
        customer_id = data.get("customer")
        plan = data.get("metadata", {}).get("plan")
        account.stripe_customer_id = customer_id
        account.stripe_subscription_id = subscription_id
        if plan:
            account.plan_tier = _tier_from_plan_key(plan)
            account.plan = _normalize_account_plan(plan)
        account.status = "active"
    elif event_type == "invoice.paid" and account:
        account.status = "active"
        plan = _plan_from_invoice(data)
        if plan:
            account.plan_tier = _tier_from_plan_key(plan)
            account.plan = _normalize_account_plan(plan)
    elif event_type == "invoice.payment_failed" and account:
        account.status = "past_due"
    elif event_type == "customer.subscription.deleted" and account:
        account.status = "canceled"
        account.stripe_subscription_id = None

    return account


async def _resolve_account(payload: dict, db: AsyncSession) -> Account | None:
    metadata_account_id = payload.get("metadata", {}).get("account_id")
    if metadata_account_id:
        account = await db.get(Account, metadata_account_id)
        if account:
            return account

    customer_id = payload.get("customer")
    if customer_id:
        account = await db.scalar(select(Account).where(Account.stripe_customer_id == customer_id))
        if account:
            return account

    subscription_id = payload.get("subscription") or payload.get("id")
    if subscription_id:
        account = await db.scalar(select(Account).where(Account.stripe_subscription_id == subscription_id))
        if account:
            return account

    return None


def _plan_from_invoice(payload: dict) -> str | None:
    lines = payload.get("lines", {}).get("data", [])
    if not lines:
        return None
    price_id = lines[0].get("price", {}).get("id")
    inverse_map = {v: k for k, v in stripe_service.plan_price_map.items()}
    return inverse_map.get(price_id)


def _normalize_account_plan(plan_key: str) -> str:
    if plan_key.endswith("_yearly") or plan_key == "yearly":
        return "yearly"
    return "monthly"


def _tier_from_plan_key(plan_key: str) -> str:
    if plan_key.startswith("founders_"):
        return "founders"
    if plan_key.startswith("team_"):
        return "team"
    if plan_key.startswith("pro_"):
        return "pro"
    return normalize_plan_tier(None)
