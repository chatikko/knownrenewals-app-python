from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.models.account import Account
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.admin import AdminAccountRead, AdminAccountUpdate
from app.schemas.common import CommonResponse, ListResponse

router = APIRouter(prefix="/admin/accounts", tags=["admin-accounts"])


@router.get("/", response_model=ListResponse[AdminAccountRead])
async def list_accounts(
    skip: int = 0,
    limit: int = 100,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[AdminAccountRead]:
    total = await db.scalar(select(func.count()).select_from(Account))
    result = await db.execute(select(Account).offset(skip).limit(limit).order_by(Account.created_at.desc()))
    items = list(result.scalars())
    return ListResponse(items=items, total=total or 0, status_code=status.HTTP_200_OK)


@router.patch("/{account_id}", response_model=CommonResponse[AdminAccountRead])
async def update_account(
    account_id: str,
    payload: AdminAccountUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[AdminAccountRead]:
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)

    await db.commit()
    await db.refresh(account)
    return CommonResponse(data=account, status_code=status.HTTP_200_OK)
