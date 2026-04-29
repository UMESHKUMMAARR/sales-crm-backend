"""
In-memory rate limiter middleware.
For production at scale, swap the store for Redis.
"""
import time
from collections import defaultdict
from threading import Lock
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings

# Thread-safe in-process store: {key: [(timestamp, count)]}
_store: dict[str, list] = defaultdict(list)
_lock = Lock()

AUTH_PATHS = {"/api/auth/login", "/api/auth/refresh"}


def _is_rate_limited(key: str, limit: int, window: int = 60) -> bool:
    now = time.time()
    with _lock:
        timestamps = _store[key]
        # Remove entries outside the window
        _store[key] = [t for t in timestamps if now - t < window]
        if len(_store[key]) >= limit:
            return True
        _store[key].append(now)
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Use IP as rate-limit key (X-Forwarded-For for proxied deployments)
        ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
        ip = ip.split(",")[0].strip()

        path = request.url.path
        is_auth = path in AUTH_PATHS

        limit = settings.AUTH_RATE_LIMIT_PER_MINUTE if is_auth else settings.RATE_LIMIT_PER_MINUTE
        key = f"{'auth' if is_auth else 'api'}:{ip}"

        if _is_rate_limited(key, limit):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Limit: {limit}/minute.",
                headers={"Retry-After": "60"},
            )

        response = await call_next(request)
        return response
