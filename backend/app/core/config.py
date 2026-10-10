from pydantic import EmailStr, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AquaFlow API"
    environment: str = "local"
    database_url: str = "postgresql+asyncpg://aquaflow:aquaflow@localhost:5432/aquaflow"
    jwt_secret: str = "development-only-change-this-secret"
    jwt_issuer: str = "aquaflow"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    late_reading_window_days: int = 7
    future_clock_skew_seconds: int = 300
    cors_origins: list[str] = ["http://localhost:3000"]
    demo_mode: bool = False
    demo_user_email: EmailStr | None = None
    demo_user_password: str = Field(default="AquaFlow-demo-123!", min_length=12, max_length=128)
    mqtt_ingestor_health_url: str | None = None
    ml_worker_health_url: str | None = None

    @model_validator(mode="after")
    def require_secure_production_secret(self) -> "Settings":
        if self.environment == "production" and (
            self.jwt_secret == "development-only-change-this-secret" or len(self.jwt_secret) < 32
        ):
            raise ValueError("JWT_SECRET must contain at least 32 characters in production")
        if self.environment == "production" and self.demo_mode:
            raise ValueError("DEMO_MODE must be disabled in production")
        return self


settings = Settings()
