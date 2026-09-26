import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict

_ephemeral_dev_secret = secrets.token_urlsafe(48)


class Settings(BaseSettings):
    app_version: str = "1.0.0"
    database_url: str = "sqlite:///./leadprophet.db"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    app_env: str = "local"
    frontend_origin: str = "http://127.0.0.1:8000"
    cors_allowed_origins: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://127.0.0.1:8000/auth/google/callback"
    jwt_secret_key: str | None = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    cache_ttl_seconds: int = 30
    redis_url: str | None = None
    search_provider: str = "stub"
    search_api_key: str | None = None
    email_provider: str = "stub"
    email_api_key: str | None = None
    email_from_address: str | None = None
    enrichment_provider: str = "internal"
    enrichment_api_key: str | None = None
    public_contact_email: str = "hello@leadprophet.app"
    public_contact_phone: str | None = None
    public_contact_city: str = "Netanya, Israel"
    public_contact_timezone: str = "Asia/Jerusalem"
    public_response_hours: str = "24-48 hours on weekdays"
    admin_notification_email: str | None = None
    cookie_samesite: str = "lax"
    cookie_secure: bool = False
    docs_enabled: bool = True
    allow_sqlite_in_production_rehearsal: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def effective_jwt_secret_key(self) -> str:
        return self.jwt_secret_key or _ephemeral_dev_secret

    @property
    def allowed_origins(self) -> list[str]:
        raw = self.cors_allowed_origins or self.frontend_origin
        return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]

    @property
    def secure_cookies(self) -> bool:
        return self.is_production or self.cookie_secure

    @property
    def expose_docs(self) -> bool:
        return self.docs_enabled and not self.is_production

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
