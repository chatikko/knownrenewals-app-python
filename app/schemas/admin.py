from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr


class AdminUserRead(BaseModel):
    id: str
    account_id: str
    email: EmailStr
    is_active: bool
    is_email_verified: bool
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    is_email_verified: bool | None = None
    is_admin: bool | None = None


class AdminAccountRead(BaseModel):
    id: str
    name: str
    owner_email: EmailStr
    plan_tier: str
    plan: str
    status: str
    stripe_customer_id: str | None
    stripe_subscription_id: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class AdminAccountUpdate(BaseModel):
    plan_tier: Literal["trialing", "founders", "pro", "team"] | None = None
    plan: Literal["monthly", "yearly"] | None = None
    status: Literal["inactive", "trialing", "active", "past_due", "canceled"] | None = None


class AdminContractRead(BaseModel):
    id: str
    account_id: str
    vendor_name: str
    renewal_type: str
    renewal_name: str
    contract_name: str | None
    renewal_date: date
    notice_period_days: int
    notice_deadline: date
    owner_email: EmailStr
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class AdminContractUpdate(BaseModel):
    status: Literal["safe", "soon", "risk"] | None = None


class AdminAuthEventRead(BaseModel):
    id: str
    user_id: str | None
    event_type: str
    ip_address: str | None
    user_agent: str | None
    success: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AdminBillingEventRead(BaseModel):
    id: str
    account_id: str | None
    stripe_event_id: str
    event_type: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
