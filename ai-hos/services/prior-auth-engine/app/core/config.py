"""Configuration for Prior Authorization Engine."""
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "prior-auth-engine"
    APP_VERSION: str = "2.0.0"
    ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    PORT: int = 8001
    SQLITE_DB_PATH: str = str(DEFAULT_DATA_DIR / "prior_auth.db")
    ALLOWED_ORIGINS: str = "*"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
