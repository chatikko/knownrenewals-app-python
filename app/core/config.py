from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "knowrenewals"
    app_env: str = "local"
    frontend_base_url: str = "http://localhost:5173"
    slack_integration_enabled: bool = True
    slack_client_id: str | None = None
    slack_client_secret: str | None = None
    slack_oauth_redirect_uri: str | None = None
    slack_post_connect_path: str = "/integrations/slack"
    slack_bot_scopes: str = "chat:write,channels:read,groups:read"
    slack_oauth_state_ttl_seconds: int = 600
    slack_max_retries: int = 3
    slack_base_backoff_seconds: float = 0.5
    slack_token_encryption_key: str | None = None
    slack_pilot_account_ids: str = ""

    database_url: str
    redis_url: str

    jwt_secret: str
    jwt_refresh_secret: str
    access_token_expire_minutes: int = 15
    refresh_token_expire_minutes: int = 60 * 24 * 7

    mail_from: str
    resend_api_key: str | None = None
    resend_max_retries: int = 3
    resend_base_backoff_seconds: float = 0.5

    stripe_api_key: str
    stripe_webhook_secret: str
    stripe_price_monthly: str
    stripe_price_yearly: str
    stripe_price_founders_monthly: str | None = None
    stripe_price_founders_yearly: str | None = None
    stripe_price_pro_monthly: str | None = None
    stripe_price_pro_yearly: str | None = None
    stripe_price_team_monthly: str | None = None
    stripe_price_team_yearly: str | None = None

    rate_limit_auth: int = 5
    rate_limit_window_seconds: int = 300

    auth_lockout_threshold: int = 5
    auth_lockout_window_seconds: int = 900

    email_verification_expire_minutes: int = 60 * 24
    resend_verification_cooldown_seconds: int = 60
    trial_period_days: int = 14
    trial_grace_period_days: int = 14

    admin_emails: str = ""

    web_concurrency: int = 2
    db_pool_size: int = 10
    db_max_overflow: int = 10

    cors_allow_origins: str = "*"
    cors_allow_methods: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    cors_allow_headers: str = "*"
    cors_allow_credentials: bool = True

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def cors_methods_list(self) -> list[str]:
        return [method.strip().upper() for method in self.cors_allow_methods.split(",") if method.strip()]

    @property
    def cors_headers_list(self) -> list[str]:
        return [header.strip() for header in self.cors_allow_headers.split(",") if header.strip()]

    @property
    def slack_pilot_account_ids_list(self) -> list[str]:
        return [account_id.strip() for account_id in self.slack_pilot_account_ids.split(",") if account_id.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
