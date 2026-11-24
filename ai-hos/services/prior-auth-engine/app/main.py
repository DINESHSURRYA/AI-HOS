"""FastAPI application entry point for Prior Authorization Engine (v2.0)."""
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.api.endpoints import router
from app.core.config import settings
from app.db.store import get_store
from app.engine.rule_engine import get_rule_engine

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
    """Load default payer policies + persisted custom policies on startup."""
    logger = structlog.get_logger()
    store = get_store()
    await store.initialize()

    engine = get_rule_engine()
    # Persist built-in defaults if DB is empty, and merge any user-created policies
    saved_policies = await store.load_all_policies()
    if not saved_policies:
        for policy in engine.policies.values():
            await store.save_policy(policy)
    else:
        for policy in saved_policies:
            engine.load_policy(policy)

    logger.info(
        "prior_auth_service_starting",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        loaded_policies=len(engine.policies),
    )
    yield
    logger.info("prior_auth_service_shutting_down")


app = FastAPI(
    title="AI-HOS Prior Authorization Engine",
    description=(
        "Automated rule-based & clinical medical-necessity prior authorization "
        "decision engine with explainable confidence scoring and payer policy management."
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
    engine = get_rule_engine()
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "loaded_policies": len(engine.policies),
        "payers": sorted({p.payer_id for p in engine.policies.values()}),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.ENV == "development",
    )
