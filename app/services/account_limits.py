from app.db.models.account import Account

DEFAULT_PLAN_TIER = "pro"

PLAN_SEAT_LIMITS: dict[str, int] = {
    "trialing": 1,
    "founders": 1,
    "pro": 5,
    "team": 15,
}


def normalize_plan_tier(plan_tier: str | None) -> str:
    if not plan_tier:
        return DEFAULT_PLAN_TIER
    value = plan_tier.strip().lower()
    return value if value in PLAN_SEAT_LIMITS else DEFAULT_PLAN_TIER


def seat_limit_for_account(account: Account) -> int:
    return PLAN_SEAT_LIMITS[normalize_plan_tier(getattr(account, "plan_tier", None))]
