from typing import Literal

from pydantic import BaseModel, HttpUrl


class CheckoutSessionRequest(BaseModel):
    plan: Literal[
        "monthly",
        "yearly",
        "founders_monthly",
        "founders_yearly",
        "pro_monthly",
        "pro_yearly",
        "team_monthly",
        "team_yearly",
    ]
    success_url: HttpUrl
    cancel_url: HttpUrl


class CheckoutSessionResponse(BaseModel):
    url: HttpUrl


class BillingActionResponse(BaseModel):
    message: str


class BillingStatusResponse(BaseModel):
    plan_tier: str | None = None
    plan: str | None = None
    status: str | None = None
    cancel_at_period_end: bool = False
    trial_days_left: int | None = None
    founders_available: bool = True
    founders_slots_remaining: int | None = None
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
