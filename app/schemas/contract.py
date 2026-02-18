from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

ContractStatus = Literal["safe", "soon", "risk"]
RenewalType = Literal["Subscription", "Contract", "License", "Domain", "Certificate", "Other"]
BillingFrequency = Literal["Monthly", "Quarterly", "Semi-Annual", "Annual", "Other"]


class ContractBase(BaseModel):
    vendor_name: str = Field(..., max_length=255)
    renewal_type: RenewalType = "Contract"
    external_contract_id: str | None = Field(default=None, max_length=64)
    category: str | None = Field(default=None, max_length=100)
    renewal_name: str | None = Field(default=None, min_length=1, max_length=255)
    contract_name: str | None = Field(default=None, max_length=255)
    start_date: date | None = None
    renewal_date: date
    billing_frequency: BillingFrequency | None = None
    contract_value: Decimal | None = Field(default=None, ge=0)
    annualized_value: Decimal | None = Field(default=None, ge=0)
    auto_renew: bool | None = None
    notice_period_days: int = Field(default=30, ge=0)
    owner_email: EmailStr | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ContractCreate(ContractBase):
    pass


class ContractUpdate(BaseModel):
    vendor_name: str | None = None
    renewal_type: RenewalType | None = None
    external_contract_id: str | None = Field(default=None, max_length=64)
    category: str | None = Field(default=None, max_length=100)
    renewal_name: str | None = Field(default=None, min_length=1, max_length=255)
    contract_name: str | None = None
    start_date: date | None = None
    renewal_date: date | None = None
    billing_frequency: BillingFrequency | None = None
    contract_value: Decimal | None = Field(default=None, ge=0)
    annualized_value: Decimal | None = Field(default=None, ge=0)
    auto_renew: bool | None = None
    notice_period_days: int | None = Field(default=None, ge=0)
    owner_email: EmailStr | None = None
    notes: str | None = Field(default=None, max_length=2000)
    status: ContractStatus | None = None


class ContractRead(ContractBase):
    renewal_name: str
    id: str
    account_id: str
    notice_deadline: date
    status: ContractStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
