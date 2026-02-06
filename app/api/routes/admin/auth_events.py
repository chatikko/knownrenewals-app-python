from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.models.auth_event import AuthEvent
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.admin import AdminAuthEventRead
from app.schemas.common import ListResponse

router = APIRouter(prefix="/admin/auth-events", tags=["admin-auth-events"])


@router.get("/", response_model=ListResponse[AdminAuthEventRead])
async def list_auth_events(
    skip: int = 0,
    limit: int = 200,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[AdminAuthEventRead]:
    total = await db.scalar(select(func.count()).select_from(AuthEvent))
    result = await db.execute(select(AuthEvent).offset(skip).limit(limit).order_by(AuthEvent.created_at.desc()))
    items = list(result.scalars())
    return ListResponse(items=items, total=total or 0, status_code=status.HTTP_200_OK)
