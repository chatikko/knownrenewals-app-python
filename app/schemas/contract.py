from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

ContractStatus = Literal["safe", "soon", "risk"]


class ContractBase(BaseModel):
    vendor_name: str = Field(..., max_length=255)
    contract_name: str | None = Field(default=None, max_length=255)
    renewal_date: date
    notice_period_days: int = Field(ge=0)
    owner_email: EmailStr


class ContractCreate(ContractBase):
    pass


class ContractUpdate(BaseModel):
    vendor_name: str | None = None
    contract_name: str | None = None
    renewal_date: date | None = None
    notice_period_days: int | None = Field(default=None, ge=0)
    owner_email: EmailStr | None = None
    status: ContractStatus | None = None


class ContractRead(ContractBase):
    id: str
    account_id: str
    notice_deadline: date
    status: ContractStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
