from datetime import datetime

from pydantic import BaseModel, Field


class SlackInstallUrlResponse(BaseModel):
    url: str


class SlackChannelRead(BaseModel):
    id: str
    name: str


class SlackStatusResponse(BaseModel):
    slack_integration_enabled: bool = True
    connected: bool
    plan_tier: str = "pro"
    instant_alerts_available: bool = True
    founders_digest_only: bool = False
    workspace_id: str | None = None
    workspace_name: str | None = None
    default_channel_id: str | None = None
    default_channel_name: str | None = None
    digest_enabled: bool = True
    instant_risk_enabled: bool = True
    instant_due_7d_enabled: bool = True
    digest_hour_local: int = 9
    timezone: str = "UTC"
    is_degraded: bool = False
    last_error_code: str | None = None
    last_error_message: str | None = None
    last_error_at: datetime | None = None
    last_test_success: bool | None = None
    last_test_sent_at: datetime | None = None


class SlackConfigUpdate(BaseModel):
    default_channel_id: str | None = Field(default=None, max_length=255)
    default_channel_name: str | None = Field(default=None, max_length=255)
    digest_enabled: bool = True
    instant_risk_enabled: bool = True
    instant_due_7d_enabled: bool = True
    digest_hour_local: int = Field(default=9, ge=0, le=23)


class SlackTestResponse(BaseModel):
    message: str
    sent_at: datetime
