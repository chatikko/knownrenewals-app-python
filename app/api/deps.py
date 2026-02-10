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

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
settings = get_settings()


async def rate_limit_auth(request: Request, redis: Redis = Depends(get_redis_client)) -> None:
    """
    Naive fixed-window limiter keyed by IP path for signup/login flows.
    """
    
    limiter_key = f"rl:{request.client.host}:{request.url.path}"
    print(limiter_key, 'limiter_key')
    try:
        current = await redis.incr(limiter_key)
    except Exception as e:
        print(e, 'redis1111111111111111111')
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


async def get_current_billing_active_user(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    account = await db.get(Account, current_user.account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    if account.status not in {"active", "trialing"}:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Active subscription required. Please update billing to continue.",
        )
    return current_user
