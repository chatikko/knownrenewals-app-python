from typing import Literal

from pydantic import BaseModel, HttpUrl


class CheckoutSessionRequest(BaseModel):
    plan: Literal["monthly", "yearly"]
    success_url: HttpUrl
    cancel_url: HttpUrl


class CheckoutSessionResponse(BaseModel):
    url: HttpUrl


class BillingStatusResponse(BaseModel):
    plan: str | None = None
    status: str | None = None
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
