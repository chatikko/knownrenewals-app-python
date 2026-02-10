from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    password: str
    account_name: str


class UserRead(UserBase):
    id: str
    account_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class MemberCreate(BaseModel):
    email: EmailStr
    password: str
    is_admin: bool = False


class MemberRead(UserBase):
    id: str
    account_id: str
    is_active: bool
    is_email_verified: bool
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True
