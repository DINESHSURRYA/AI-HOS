"""FastAPI application for Clinical Documentation AI Service (v2.0)."""
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.api.endpoints import router
from app.core.asr_pipeline import get_asr_pipeline
from app.core.config import settings
from app.core.nlp_pipeline import get_nlp_pipeline
from app.db.mongodb import get_db

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and warm lightweight pipelines on startup."""
    logger = structlog.get_logger()
    await get_db().initialize()
    logger.info(
        "service_starting",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        env=settings.ENV,
        storage=get_db().backend,
    )
    yield
    logger.info("service_shutting_down", app=settings.APP_NAME)


app = FastAPI(
    title="AI-HOS Clinical Documentation AI",
    description=(
        "HIPAA-compliant clinical voice/text documentation, medical entity coding "
        "(ICD-10 / RxNorm / CPT), structured SOAP note generation, and FHIR R4 export."
    ),
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

origins = (
    ["*"]
    if settings.ALLOWED_ORIGINS.strip() == "*"
    else [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "storage_backend": get_db().backend,
        "asr_engine": get_asr_pipeline().engine_name,
        "nlp_engine": get_nlp_pipeline().engine_name,
        "llm_mode": settings.LLM_MODEL if settings.ENABLE_LLM_GENERATION else "local-clinical-engine-v2",
        "phi_redaction_enabled": settings.PHI_REDACTION_ENABLED,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.ENV == "development",
    )
