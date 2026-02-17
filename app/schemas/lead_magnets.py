from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LeadMagnetSubmitRequest(BaseModel):
    email: EmailStr
    source_path: str | None = Field(default=None, max_length=512)
    utm_source: str | None = Field(default=None, max_length=255)
    utm_medium: str | None = Field(default=None, max_length=255)
    utm_campaign: str | None = Field(default=None, max_length=255)
    utm_term: str | None = Field(default=None, max_length=255)
    utm_content: str | None = Field(default=None, max_length=255)
    referrer: str | None = Field(default=None, max_length=1024)


class LeadMagnetSubmitResponse(BaseModel):
    message: str
    status: Literal["sent", "failed", "skipped"]


class LeadMagnetStatsResponse(BaseModel):
    total_submissions: int
    successful_sends: int
    unique_emails: int
    failed_deliveries: int
    skipped_submissions: int


class LeadMagnetDownloadRead(BaseModel):
    id: str
    magnet_key: str
    email: EmailStr
    status: str
    sent_at: datetime | None
    failure_reason: str | None
    source_path: str | None
    utm_source: str | None
    utm_medium: str | None
    utm_campaign: str | None
    utm_term: str | None
    utm_content: str | None
    referrer: str | None
    created_at: datetime

    class Config:
        from_attributes = True
