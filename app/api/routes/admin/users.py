from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.admin import AdminUserRead, AdminUserUpdate
from app.schemas.common import CommonResponse, ListResponse

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.get("/", response_model=ListResponse[AdminUserRead])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[AdminUserRead]:
    total = await db.scalar(select(func.count()).select_from(User))
    result = await db.execute(select(User).offset(skip).limit(limit).order_by(User.created_at.desc()))
    items = list(result.scalars())
    return ListResponse(items=items, total=total or 0, status_code=status.HTTP_200_OK)


@router.patch("/{user_id}", response_model=CommonResponse[AdminUserRead])
async def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[AdminUserRead]:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return CommonResponse(data=user, status_code=status.HTTP_200_OK)
