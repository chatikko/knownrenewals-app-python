from __future__ import annotations

import stripe
from fastapi import HTTPException, status
from stripe.error import SignatureVerificationError

from app.core.config import get_settings

settings = get_settings()
stripe.api_key = settings.stripe_api_key


class StripeService:
    def __init__(self) -> None:
        self.webhook_secret = settings.stripe_webhook_secret
        founders_monthly = settings.stripe_price_founders_monthly or settings.stripe_price_monthly
        founders_yearly = settings.stripe_price_founders_yearly or settings.stripe_price_yearly
        pro_monthly = settings.stripe_price_pro_monthly or settings.stripe_price_monthly
        pro_yearly = settings.stripe_price_pro_yearly or settings.stripe_price_yearly
        team_monthly = settings.stripe_price_team_monthly or settings.stripe_price_monthly
        team_yearly = settings.stripe_price_team_yearly or settings.stripe_price_yearly
        self.plan_price_map = {
            "founders_monthly": founders_monthly,
            "founders_yearly": founders_yearly,
            "pro_monthly": pro_monthly,
            "pro_yearly": pro_yearly,
            "team_monthly": team_monthly,
            "team_yearly": team_yearly,
            "monthly": pro_monthly,
            "yearly": pro_yearly,
        }

    def create_checkout_session(
        self,
        account_id: str,
        plan: str,
        success_url: str,
        cancel_url: str,
        customer_id: str | None,
    ) -> stripe.checkout.Session:
        price = self.plan_price_map.get(plan)
        if not price:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported plan")

        create_kwargs = {
            "payment_method_types": ["card"],
            "mode": "subscription",
            "line_items": [{"price": price, "quantity": 1}],
            "metadata": {"account_id": account_id, "plan": plan},
            "success_url": success_url,
            "cancel_url": cancel_url,
            "subscription_data": {"metadata": {"account_id": account_id}},
            "allow_promotion_codes": True,
        }
        # `customer_creation` is only valid for `payment` mode. In subscription mode,
        # Stripe creates a customer automatically when `customer` is not provided.
        if customer_id:
            create_kwargs["customer"] = customer_id

        try:
            session = stripe.checkout.Session.create(**create_kwargs)
            return session
        except stripe.error.StripeError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Stripe checkout session failed: {getattr(exc, 'user_message', None) or str(exc)}",
            ) from exc

    def parse_event(self, payload: bytes, signature: str):
        try:
            return stripe.Webhook.construct_event(payload, signature, self.webhook_secret)
        except (ValueError, SignatureVerificationError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook") from exc

    def get_subscription(self, subscription_id: str) -> stripe.Subscription:
        try:
            return stripe.Subscription.retrieve(subscription_id)
        except stripe.error.StripeError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Stripe subscription lookup failed: {getattr(exc, 'user_message', None) or str(exc)}",
            ) from exc

    def set_cancel_at_period_end(self, subscription_id: str, value: bool) -> stripe.Subscription:
        try:
            return stripe.Subscription.modify(subscription_id, cancel_at_period_end=value)
        except stripe.error.StripeError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Stripe subscription update failed: {getattr(exc, 'user_message', None) or str(exc)}",
            ) from exc


stripe_service = StripeService()
