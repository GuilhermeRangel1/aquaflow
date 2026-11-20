from pathlib import Path

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
    demo_dataset_path: Path | None = None
    demo_user_email: EmailStr | None = None
    demo_user_password: str = Field(default="AquaFlow-demo-123!", min_length=8, max_length=128)
    mqtt_ingestor_health_url: str | None = None
    ml_worker_health_url: str | None = None
    ml_artifacts_dir: Path = Path("data/ml")
    mlflow_tracking_uri: str | None = None

    @model_validator(mode="after")
    def require_secure_production_secret(self) -> "Settings":
        if self.environment == "production" and (
            self.jwt_secret == "development-only-change-this-secret" or len(self.jwt_secret) < 32
        ):
            raise ValueError("JWT_SECRET must contain at least 32 characters in production")
        if self.environment == "production" and self.demo_mode:
            raise ValueError("DEMO_MODE must be disabled in production")
        if len(self.demo_user_password) < 12 and not (
            self.environment == "local"
            and self.demo_mode
            and self.demo_dataset_path is not None
            and self.demo_user_email == "admin@admin.com"
        ):
            raise ValueError("Short seed passwords are only allowed for the local hybrid account")
        return self


settings = Settings()
