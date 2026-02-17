from typing import NamedTuple

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_redis_client
from app.core.security import decode_token
from app.db.models.account import Account
from app.db.models.user import User
from app.db.session import get_db
from app.services.billing_access import resolve_billing_access_state

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
settings = get_settings()


class AccountAdminContext(NamedTuple):
    user: User
    account: Account


async def rate_limit_auth(request: Request, redis: Redis = Depends(get_redis_client)) -> None:
    """
    Naive fixed-window limiter keyed by IP path for signup/login flows.
    """
    limiter_key = f"rl:{request.client.host}:{request.url.path}"
    try:
        current = await redis.incr(limiter_key)
    except Exception:
        return
    if current == 1:
        await redis.expire(limiter_key, settings.rate_limit_window_seconds)
    if current > settings.rate_limit_auth:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests, slow down.")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_token(token, settings.jwt_secret, "access")
    except JWTError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials") from exc

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user = await db.scalar(select(User).where(User.id == user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    return user


async def get_current_admin(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await get_current_user(token=token, db=db)
    admin_emails = {email.strip().lower() for email in settings.admin_emails.split(",") if email.strip()}
    if not user.is_admin and user.email.lower() not in admin_emails:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def get_current_account_admin(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountAdminContext:
    account = await db.get(Account, current_user.account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    is_owner = current_user.email.strip().lower() == account.owner_email.strip().lower()
    if not (current_user.is_admin or is_owner):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account admin access required")

    return AccountAdminContext(user=current_user, account=account)


async def get_current_billing_read_user(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    account = await db.get(Account, current_user.account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    access = resolve_billing_access_state(account, settings)
    if not access.read_allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription required. Please update billing to continue.",
        )
    return current_user


async def get_current_billing_write_user(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    account = await db.get(Account, current_user.account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    access = resolve_billing_access_state(account, settings)
    if not access.read_allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription required. Please update billing to continue.",
        )
    if not access.write_allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Trial expired. Account is in read-only mode. Upgrade to continue editing.",
        )
    return current_user


# Backward compatibility for existing imports.
get_current_billing_active_user = get_current_billing_write_user
