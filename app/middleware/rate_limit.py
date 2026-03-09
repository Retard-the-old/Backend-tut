"""Redis-backed rate limiting middleware for FastAPI.

Usage in main.py:
    from app.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)

Or apply per-route with the dependency:
    from app.middleware.rate_limit import rate_limit
    @router.post("/login", dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60))])
"""
from __future__ import annotations
import time, logging
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger(__name__)

# Shared async Redis connection
_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Global middleware (applies default limits by path pattern) ──

# Limits: (max_requests, window_seconds)
ROUTE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/v1/auth/login": (5, 60),         # 5 per minute
    "/api/v1/auth/register": (3, 60),       # 3 per minute
    "/api/v1/auth/refresh": (10, 60),       # 10 per minute
    "/api/v1/chat/messages": (20, 60),      # 20 per minute
    "/api/v1/webhooks/mamopay": (30, 60),   # 30 per minute
}
DEFAULT_LIMIT = (60, 60)  # 60 per minute for everything else


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        ip = _client_ip(request)
        max_req, window = ROUTE_LIMITS.get(path, DEFAULT_LIMIT)
        key = f"rl:{ip}:{path}"

        try:
            r = await get_redis()
            current = await r.incr(key)
            if current == 1:
                await r.expire(key, window)
            ttl = await r.ttl(key)

            if current > max_req:
                logger.warning("Rate limit hit: %s on %s (%d/%d)", ip, path, current, max_req)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again later."},
                    headers={"Retry-After": str(ttl), "X-RateLimit-Limit": str(max_req), "X-RateLimit-Remaining": "0"},
                )
        except Exception as e:
            logger.error("Rate limit Redis error (allowing request): %s", e)

        response = await call_next(request)
        return response


# ── Per-route dependency (for custom limits on specific endpoints) ──

def rate_limit(max_requests: int = 10, window_seconds: int = 60):
    async def _check(request: Request):
        ip = _client_ip(request)
        path = request.url.path
        key = f"rl:{ip}:{path}:dep"
        try:
            r = await get_redis()
            current = await r.incr(key)
            if current == 1:
                await r.expire(key, window_seconds)
            if current > max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please try again later.",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Rate limit dep Redis error: %s", e)
    return _check
