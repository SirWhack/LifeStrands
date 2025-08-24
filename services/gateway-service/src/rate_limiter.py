import time
import asyncio
from typing import Dict, Optional
from collections import defaultdict, deque
from fastapi import Request, HTTPException
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple in-memory rate limiter"""

    def __init__(self, requests_per_minute: int = 100):
        self.requests_per_minute = requests_per_minute
        self.requests = defaultdict(deque)
        self.cleanup_interval = 60  # seconds
        self.last_cleanup = time.time()

    def is_allowed(self, client_id: str) -> bool:
        """Check if request is allowed for client"""
        now = time.time()
        minute_ago = now - 60

        # Periodic cleanup
        if now - self.last_cleanup > self.cleanup_interval:
            self._cleanup_old_requests()
            self.last_cleanup = now

        # Remove requests older than 1 minute
        client_requests = self.requests[client_id]
        while client_requests and client_requests[0] < minute_ago:
            client_requests.popleft()

        # Check limit
        if len(client_requests) >= self.requests_per_minute:
            return False

        # Add current request
        client_requests.append(now)
        return True

    def _cleanup_old_requests(self):
        """Remove expired request records"""
        now = time.time()
        minute_ago = now - 60
        clients_to_remove = []
        for client_id, requests in self.requests.items():
            while requests and requests[0] < minute_ago:
                requests.popleft()
            if not requests:
                clients_to_remove.append(client_id)
        for client_id in clients_to_remove:
            del self.requests[client_id]


# Global rate limiter instance
rate_limiter = RateLimiter(requests_per_minute=100)


async def rate_limit_middleware(request: Request, call_next):
    """FastAPI middleware for rate limiting"""
    try:
        # Prefer first IP in X-Forwarded-For when behind a proxy
        xff = request.headers.get("X-Forwarded-For")
        client_ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")
        # Use user-id header if present (after auth)
        user_id = request.headers.get("user-id")
        client_id = user_id if user_id else client_ip

        # Check rate limit
        if not rate_limiter.is_allowed(client_id):
            logger.warning(f"Rate limit exceeded for client {client_id}")
            reset = 60
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
                headers={
                    "Retry-After": str(reset),
                    "X-RateLimit-Limit": str(rate_limiter.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset),
                },
            )

        # Process request
        response = await call_next(request)
        # Attach rate limit headers
        try:
            client_reqs = rate_limiter.requests.get(client_id, [])
            remaining = max(0, rate_limiter.requests_per_minute - len(client_reqs))
            response.headers["X-RateLimit-Limit"] = str(rate_limiter.requests_per_minute)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
        except Exception:
            pass
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rate limiting error: {e}")
        response = await call_next(request)
        return response
