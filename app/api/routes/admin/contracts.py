from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.models.contract import Contract
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.admin import AdminContractRead, AdminContractUpdate
from app.schemas.common import CommonResponse, ListResponse

router = APIRouter(prefix="/admin/contracts", tags=["admin-contracts"])


@router.get("/", response_model=ListResponse[AdminContractRead])
async def list_contracts(
    skip: int = 0,
    limit: int = 100,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[AdminContractRead]:
    total = await db.scalar(select(func.count()).select_from(Contract))
    result = await db.execute(select(Contract).offset(skip).limit(limit).order_by(Contract.created_at.desc()))
    items = list(result.scalars())
    return ListResponse(items=items, total=total or 0, status_code=status.HTTP_200_OK)


@router.patch("/{contract_id}", response_model=CommonResponse[AdminContractRead])
async def update_contract(
    contract_id: str,
    payload: AdminContractUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[AdminContractRead]:
    contract = await db.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(contract, field, value)

    await db.commit()
    await db.refresh(contract)
    return CommonResponse(data=contract, status_code=status.HTTP_200_OK)
