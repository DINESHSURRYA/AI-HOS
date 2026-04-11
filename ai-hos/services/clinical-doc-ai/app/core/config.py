"""HIPAA-compliant configuration with secrets management."""
from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    """Application settings loaded from environment."""
    
    # Service
    APP_NAME: str = "clinical-doc-ai"
    LOG_LEVEL: str = "INFO"
    ENV: str = "development"
    
    # MongoDB - For unstructured clinical notes
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "clinical_notes"
    
    # PostgreSQL - For FHIR resources and audit
    POSTGRES_URL: str = "postgresql://postgres:postgres@localhost:5432/fhir_audit"
    
    # Redis - For caching and session management
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # ASR Configuration
    WHISPER_MODEL: str = "large-v3"  # or "medium" for faster inference
    WHISPER_DEVICE: str = "cpu"  # "cuda" for GPU
    WHISPER_COMPUTE_TYPE: str = "int8"  # "float16" for GPU
    WHISPER_BATCH_SIZE: int = 16
    WHISPER_LANGUAGE: str = "en"
    
    # LLM Configuration (Ollama/vLLM compatible)
    LLM_BASE_URL: str = "http://localhost:11434/v1"
    LLM_API_KEY: str = "local"
    LLM_MODEL: str = "llama3:70b"  # or "mixtral" for smaller footprint
    LLM_MAX_TOKENS: int = 2048
    LLM_TEMPERATURE: float = 0.1  # Low temp for clinical accuracy
    
    # Security
    ENCRYPTION_KEY: str = os.urandom(32).hex()  # Generate properly in prod
    PHI_REDACTION_ENABLED: bool = True
    
    # Feature Flags
    ENABLE_REALTIME_STREAMING: bool = True
    ENABLE_LLM_GENERATION: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()


settings = get_settings()
