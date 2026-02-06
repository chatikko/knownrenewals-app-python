from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import rate_limit_auth
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.db.models.account import Account
from app.db.models.auth_event import AuthEvent
from app.db.models.refresh_token import RefreshToken
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RefreshRequest, SignupRequest, SignupResponse, TokenPair, VerifyEmailRequest
from app.schemas.common import CommonResponse
from app.services.email import email_service
from app.core.redis import get_redis_client

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/signup", response_model=CommonResponse[SignupResponse], dependencies=[Depends(rate_limit_auth)])
async def signup(payload: SignupRequest, request: Request, db: AsyncSession = Depends(get_db)) -> CommonResponse[SignupResponse]:
    existing_user = await db.scalar(select(User).where(User.email == payload.email))
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    _ensure_password_policy(payload.password)
    account = Account(name=payload.account_name, owner_email=payload.email, status="trialing")
    user = User(email=payload.email, password_hash=get_password_hash(payload.password))
    verification_token = _attach_email_verification(user)
    account.users.append(user)

    db.add(account)
    await db.commit()
    await db.refresh(user)

    await email_service.send_verification_email(user.email, verification_token)
    await _log_auth_event(db, user.id, "signup", request, True)
    return CommonResponse(
        data=SignupResponse(message="Signup successful. Check your email to verify your account."),
        status_code=status.HTTP_200_OK,
    )


@router.post("/login", response_model=CommonResponse[TokenPair], dependencies=[Depends(rate_limit_auth)])
async def login(
    payload: LoginRequest,
    request: Request,
    redis: Redis = Depends(get_redis_client),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[TokenPair]:
    user = await db.scalar(select(User).where(User.email == payload.email))
    if not user:
        await _log_auth_event(db, None, "login", request, False)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    await _enforce_lockout(user.id, redis)
    if not verify_password(payload.password, user.password_hash):
        await _record_failed_login(user.id, redis)
        await _log_auth_event(db, user.id, "login", request, False)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_email_verified:
        await _log_auth_event(db, user.id, "login", request, False)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified")

    await _clear_failed_logins(user.id, redis)
    await _log_auth_event(db, user.id, "login", request, True)
    tokens = await _issue_tokens(user.id, db)
    return CommonResponse(data=tokens, status_code=status.HTTP_200_OK)


@router.post("/refresh", response_model=CommonResponse[TokenPair])
async def refresh(payload: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)) -> CommonResponse[TokenPair]:
    try:
        decoded = decode_token(payload.refresh_token, settings.jwt_refresh_secret, "refresh")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    user_id = decoded.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        await _log_auth_event(db, user_id, "refresh", request, False)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    token_hash = _hash_token(payload.refresh_token)
    stored = await db.scalar(
        select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.token_hash == token_hash)
    )
    if not stored or stored.revoked_at:
        await _log_auth_event(db, user_id, "refresh", request, False)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if stored.expires_at < _now_utc():
        stored.revoked_at = _now_utc()
        await db.commit()
        await _log_auth_event(db, user_id, "refresh", request, False)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired refresh token")

    stored.revoked_at = _now_utc()
    new_tokens = await _issue_tokens(user.id, db)
    stored.replaced_by = _hash_token(new_tokens.refresh_token)
    await db.commit()
    await _log_auth_event(db, user_id, "refresh", request, True)
    return CommonResponse(data=new_tokens, status_code=status.HTTP_200_OK)


@router.post("/verify-email", response_model=CommonResponse[SignupResponse])
async def verify_email(
    payload: VerifyEmailRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> CommonResponse[SignupResponse]:
    token_hash = _hash_token(payload.token)
    user = await db.scalar(select(User).where(User.email_verification_hash == token_hash))
    if not user or user.is_email_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification token")

    if not user.email_verification_expires_at or user.email_verification_expires_at < _now_utc():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification token expired")

    user.is_email_verified = True
    user.email_verification_hash = None
    user.email_verification_expires_at = None
    await db.commit()
    await _log_auth_event(db, user.id, "verify_email", request, True)
    return CommonResponse(
        data=SignupResponse(message="Email verified. You can now log in."),
        status_code=status.HTTP_200_OK,
    )


async def _issue_tokens(user_id: str, db: AsyncSession) -> TokenPair:
    access = create_access_token(user_id, settings.jwt_secret, settings.access_token_expire_minutes)
    refresh = create_refresh_token(user_id, settings.jwt_refresh_secret, settings.refresh_token_expire_minutes)
    await _store_refresh_token(user_id, refresh, db)
    return TokenPair(access_token=access, refresh_token=refresh)


def _ensure_password_policy(password: str) -> None:
    if len(password) < 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 12 characters")
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at most 72 bytes",
        )


async def _store_refresh_token(user_id: str, refresh_token: str, db: AsyncSession) -> None:
    token_hash = _hash_token(refresh_token)
    expires_at = _now_utc() + timedelta(minutes=settings.refresh_token_expire_minutes)
    db.add(RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at))
    await db.commit()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _attach_email_verification(user: User) -> str:
    token = secrets.token_urlsafe(32)
    user.email_verification_hash = _hash_token(token)
    user.email_verification_expires_at = _now_utc() + timedelta(minutes=settings.email_verification_expire_minutes)
    user.is_email_verified = False
    return token


def _is_admin_email(email: str) -> bool:
    admin_emails = {addr.strip().lower() for addr in settings.admin_emails.split(",") if addr.strip()}
    return email.lower() in admin_emails


async def _log_auth_event(db: AsyncSession, user_id: str | None, event_type: str, request: Request, success: bool) -> None:
    event = AuthEvent(
        user_id=user_id,
        event_type=event_type,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        success=success,
    )
    db.add(event)
    await db.commit()


async def _enforce_lockout(user_id: str, redis: Redis) -> None:
    key = f"auth:fail:{user_id}"
    current = await redis.get(key)
    if current and int(current) >= settings.auth_lockout_threshold:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Account locked. Try later.")


async def _record_failed_login(user_id: str, redis: Redis) -> None:
    key = f"auth:fail:{user_id}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, settings.auth_lockout_window_seconds)


async def _clear_failed_logins(user_id: str, redis: Redis) -> None:
    key = f"auth:fail:{user_id}"
    await redis.delete(key)
