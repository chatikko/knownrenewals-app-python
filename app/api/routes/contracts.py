from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models.contract import Contract
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.common import CommonResponse, ListResponse
from app.schemas.contract import ContractCreate, ContractRead, ContractUpdate

router = APIRouter(prefix="/contracts", tags=["contracts"])


@router.get("/", response_model=ListResponse[ContractRead])
async def list_contracts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ListResponse[ContractRead]:
    result = await db.execute(
        select(Contract).where(Contract.account_id == current_user.account_id).order_by(Contract.notice_deadline)
    )
    items = list(result.scalars())
    return ListResponse(items=items, total=len(items), status_code=status.HTTP_200_OK)


@router.post("/", response_model=CommonResponse[ContractRead], status_code=status.HTTP_201_CREATED)
async def create_contract(
    payload: ContractCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[ContractRead]:
    contract = Contract(
        account_id=current_user.account_id,
        **payload.model_dump(),
    )
    contract.notice_deadline = Contract.compute_notice_deadline(payload.renewal_date, payload.notice_period_days)
    contract.status = _derive_status(contract.notice_deadline)

    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return CommonResponse(data=contract, status_code=status.HTTP_201_CREATED)


@router.get("/{contract_id}", response_model=CommonResponse[ContractRead])
async def get_contract(
    contract_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[ContractRead]:
    contract = await _get_contract_or_404(contract_id, current_user, db)
    return CommonResponse(data=contract, status_code=status.HTTP_200_OK)


@router.put("/{contract_id}", response_model=CommonResponse[ContractRead])
async def update_contract(
    contract_id: str,
    payload: ContractUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[ContractRead]:
    contract = await _get_contract_or_404(contract_id, current_user, db)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(contract, field, value)

    if "renewal_date" in updates or "notice_period_days" in updates:
        contract.notice_deadline = Contract.compute_notice_deadline(contract.renewal_date, contract.notice_period_days)

    contract.status = _derive_status(contract.notice_deadline)
    await db.commit()
    await db.refresh(contract)
    return CommonResponse(data=contract, status_code=status.HTTP_200_OK)


@router.delete("/{contract_id}", response_model=CommonResponse[None], status_code=status.HTTP_200_OK)
async def delete_contract(
    contract_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CommonResponse[None]:
    contract = await _get_contract_or_404(contract_id, current_user, db)
    await db.delete(contract)
    await db.commit()
    return CommonResponse(message="Contract deleted", status_code=status.HTTP_200_OK)


async def _get_contract_or_404(contract_id: str, current_user: User, db: AsyncSession) -> Contract:
    contract = await db.get(Contract, contract_id)
    if not contract or contract.account_id != current_user.account_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return contract


def _derive_status(notice_deadline: date) -> str:
    days_until = (notice_deadline - date.today()).days
    if days_until < 0 or days_until <= 7:
        return "risk"
    if days_until <= 30:
        return "soon"
    return "safe"
