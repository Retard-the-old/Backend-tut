from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.api.router import api_router
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware
from app.services.mamopay_sync import start_sync_scheduler
import logging
import asyncio

setup_logging()
logger = logging.getLogger(__name__)


def run_migrations():
    """Run alembic migrations at startup. Logs errors but does not crash the server."""
    try:
        from alembic.config import Config
        from alembic import command
        import os
        # Use absolute path so this works regardless of working directory
        base_dir = os.path.dirname(os.path.abspath(__file__))
        alembic_cfg = Config(os.path.join(base_dir, "alembic.ini"))
        alembic_cfg.set_main_option("script_location", os.path.join(base_dir, "alembic"))
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations applied successfully")
    except Exception as e:
        logger.error(f"Migration failed (server will still start): {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Tutorii API starting up")
    run_migrations()
    # Start background MamoPay sync — runs every hour to catch missed webhooks
    sync_task = asyncio.create_task(start_sync_scheduler())
    yield
    sync_task.cancel()
    logger.info("Tutorii API shutting down")

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.APP_NAME}
