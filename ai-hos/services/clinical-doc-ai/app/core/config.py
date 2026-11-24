"""HIPAA-compliant configuration with secrets management and local-first defaults."""
from functools import lru_cache
from pathlib import Path
import secrets
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    # Service
    APP_NAME: str = "clinical-doc-ai"
    APP_VERSION: str = "2.0.0"
    LOG_LEVEL: str = "INFO"
    ENV: str = "development"
    PORT: int = 8000

    # Storage: "sqlite" (zero-config persistent default) or "mongodb"
    STORAGE_BACKEND: str = "sqlite"
    SQLITE_DB_PATH: str = str(DEFAULT_DATA_DIR / "clinical_doc.db")

    # MongoDB - Optional external document store
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "clinical_notes"

    # PostgreSQL - Optional FHIR resources and audit store
    POSTGRES_URL: str = "postgresql://postgres:postgres@localhost:5432/fhir_audit"

    # Redis - Optional caching and session store
    REDIS_URL: str = "redis://localhost:6379/0"

    # ASR Configuration
    ENABLE_WHISPERX: bool = False  # Set true when whisperx + torch are installed
    WHISPER_MODEL: str = "medium"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_BATCH_SIZE: int = 16
    WHISPER_LANGUAGE: str = "en"

    # NLP Configuration
    ENABLE_TRANSFORMER_NER: bool = False  # Set true when scispacy/transformers are installed

    # LLM Configuration (Ollama / vLLM / OpenAI-compatible)
    ENABLE_LLM_GENERATION: bool = False  # Auto-uses local structured clinical engine if False or unreachable
    LLM_BASE_URL: str = "http://localhost:11434/v1"
    LLM_API_KEY: str = "local"
    LLM_MODEL: str = "llama3.1:8b"
    LLM_MAX_TOKENS: int = 2048
    LLM_TEMPERATURE: float = 0.1
    LLM_TIMEOUT_SECONDS: float = 15.0

    # Security & HIPAA
    ENCRYPTION_KEY: str = Field(default_factory=lambda: secrets.token_hex(32))
    PHI_REDACTION_ENABLED: bool = True

    # CORS
    ALLOWED_ORIGINS: str = "*"

    # Feature Flags
    ENABLE_REALTIME_STREAMING: bool = True


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()


settings = get_settings()
