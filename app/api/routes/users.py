from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_billing_active_user
from app.core.config import get_settings
from app.core.security import get_password_hash
from app.db.models.account import Account
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.common import CommonResponse, ListResponse
from app.schemas.user import MemberCreate, MemberRead
from app.services.account_limits import seat_limit_for_account
from app.services.email import email_service

router = APIRouter(prefix="/users", tags=["users"])
settings = get_settings()


@router.get("/members", response_model=ListResponse[MemberRead])
async def list_members(
    current_user: User = Depends(get_current_billing_active_user),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[MemberRead]:
    account = await db.get(Account, current_user.account_id)
    _ensure_member_manager(current_user, account)

    result = await db.execute(
        select(User).where(User.account_id == current_user.account_id).order_by(User.created_at.asc())
    )
    items = list(result.scalars())
    return ListResponse(items=items, total=len(items), status_code=status.HTTP_200_OK)


@router.post("/members", response_model=CommonResponse[MemberRead], status_code=status.HTTP_201_CREATED)
async def create_member(
    payload: MemberCreate,
    current_user: User = Depends(get_current_billing_active_user),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[MemberRead]:
    account = await db.get(Account, current_user.account_id)
    _ensure_member_manager(current_user, account)

    normalized_email = _normalize_email(payload.email)
    existing_user = await db.scalar(select(User).where(User.email == normalized_email))
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    _ensure_password_policy(payload.password)
    user_count = await db.scalar(select(func.count()).select_from(User).where(User.account_id == current_user.account_id))
    seat_limit = seat_limit_for_account(account)
    if (user_count or 0) >= seat_limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Seat limit reached for {account.plan_tier} plan ({seat_limit} users).",
        )

    user = User(
        account_id=current_user.account_id,
        email=normalized_email,
        password_hash=get_password_hash(payload.password),
        is_active=True,
        is_email_verified=False,
        is_admin=payload.is_admin,
    )
    verification_token = _attach_email_verification(user)
    db.add(user)
    await db.flush()

    try:
        await email_service.send_verification_email(user.email, verification_token)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User created in request, but verification email could not be sent. Please retry.",
        ) from exc

    await db.commit()
    await db.refresh(user)
    return CommonResponse(
        data=user,
        message="Member created. Verification email sent.",
        status_code=status.HTTP_201_CREATED,
    )


@router.delete("/members/{user_id}", response_model=CommonResponse[None], status_code=status.HTTP_200_OK)
async def delete_member(
    user_id: str,
    current_user: User = Depends(get_current_billing_active_user),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[None]:
    account = await db.get(Account, current_user.account_id)
    _ensure_member_manager(current_user, account)

    target = await db.get(User, user_id)
    if not target or target.account_id != current_user.account_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if _normalize_email(target.email) == _normalize_email(account.owner_email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove account owner")

    if target.is_admin:
        admin_count = await db.scalar(
            select(func.count()).select_from(User).where(User.account_id == current_user.account_id, User.is_admin.is_(True))
        )
        if (admin_count or 0) <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove the last admin")

    await db.delete(target)
    await db.commit()
    return CommonResponse(message="Member removed", status_code=status.HTTP_200_OK)


def _ensure_member_manager(current_user: User, account: Account | None) -> None:
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    is_owner = _normalize_email(current_user.email) == _normalize_email(account.owner_email)
    if not (current_user.is_admin or is_owner):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _ensure_password_policy(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters")
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at most 72 bytes")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _attach_email_verification(user: User) -> str:
    token = secrets.token_urlsafe(32)
    user.email_verification_hash = _hash_token(token)
    user.email_verification_expires_at = _now_utc() + timedelta(minutes=settings.email_verification_expire_minutes)
    return token
