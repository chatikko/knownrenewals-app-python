from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "knowrenewals"
    app_env: str = "local"

    database_url: str
    redis_url: str

    jwt_secret: str
    jwt_refresh_secret: str
    access_token_expire_minutes: int = 15
    refresh_token_expire_minutes: int = 60 * 24 * 7

    smtp_host: str
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_from: str

    stripe_api_key: str
    stripe_webhook_secret: str
    stripe_price_monthly: str
    stripe_price_yearly: str

    rate_limit_auth: int = 5
    rate_limit_window_seconds: int = 300

    auth_lockout_threshold: int = 5
    auth_lockout_window_seconds: int = 900

    email_verification_expire_minutes: int = 60 * 24

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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
