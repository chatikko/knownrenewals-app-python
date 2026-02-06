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
        self.plan_price_map = {
            "monthly": settings.stripe_price_monthly,
            "yearly": settings.stripe_price_yearly,
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


stripe_service = StripeService()
