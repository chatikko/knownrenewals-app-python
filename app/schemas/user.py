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
