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
import concurrent.futures

setup_logging()
logger = logging.getLogger(__name__)


def _run_migrations_sync():
    """Synchronous migration runner — must be called from a thread (not the event loop)."""
    try:
        from alembic.config import Config
        from alembic import command
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        alembic_cfg = Config(os.path.join(base_dir, "alembic.ini"))
        alembic_cfg.set_main_option("script_location", os.path.join(base_dir, "alembic"))
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations applied successfully")
    except Exception as e:
        logger.error(f"Migration failed (server will still start): {e}", exc_info=True)


async def run_migrations():
    """Run alembic in a thread so asyncio.run() inside env.py doesn't conflict
    with the already-running FastAPI event loop."""
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        await loop.run_in_executor(pool, _run_migrations_sync)


async def bootstrap_admin():
    """If ADMIN_EMAIL env var is set, ensure that user has role='admin'."""
    email = (settings.ADMIN_EMAIL or "").strip().lower()
    if not email:
        return
    try:
        from app.db.database import AsyncSessionLocal
        from sqlalchemy import select, update
        from app.models.user import User
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if user is None:
                logger.warning("bootstrap_admin: no user found with email=%s", email)
                return
            if user.role != "admin":
                await db.execute(
                    update(User).where(User.email == email).values(role="admin")
                )
                await db.commit()
                logger.info("bootstrap_admin: promoted %s to admin", email)
            else:
                logger.info("bootstrap_admin: %s is already admin", email)
    except Exception as e:
        logger.error("bootstrap_admin failed: %s", e, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Tutorii API starting up")
    await run_migrations()
    await bootstrap_admin()
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
