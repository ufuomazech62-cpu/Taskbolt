# -*- coding: utf-8 -*-
"""Rate Limiting for Multi-Tenant SaaS.

Implements per-tenant rate limiting using:
- Token bucket algorithm
- Redis for distributed rate limiting
- Fallback to in-memory for single-instance

Features:
- Per-tenant quotas
- Different limits for different endpoints
- Graceful degradation
"""
from __future__ import annotations

import asyncio
import time
import logging
import os
from dataclasses import dataclass
from typing import Optional, Dict, Callable
from functools import wraps

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Configuration
REDIS_URL = os.environ.get("REDIS_URL", "")
RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "true"

# ============================================================================
# RATE LIMIT BACKENDS
# ============================================================================

class RateLimitBackend:
    """Abstract base class for rate limit backends."""
    
    async def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        """Check if request is allowed.
        
        Args:
            key: Unique identifier (e.g., tenant_id)
            limit: Maximum requests per window
            window: Time window in seconds
            
        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        raise NotImplementedError


class InMemoryBackend(RateLimitBackend):
    """In-memory rate limit backend using token bucket.
    
    Suitable for single-instance deployments.
    """
    
    def __init__(self):
        self._buckets: Dict[str, list[float]] = {}
        self._lock = asyncio.Lock()
    
    async def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        async with self._lock:
            now = time.time()
            window_start = now - window
            
            # Get or create bucket
            if key not in self._buckets:
                self._buckets[key] = []
            
            bucket = self._buckets[key]
            
            # Remove expired entries
            bucket[:] = [ts for ts in bucket if ts > window_start]
            
            # Check if allowed
            if len(bucket) < limit:
                bucket.append(now)
                return True, limit - len(bucket) - 1
            
            return False, 0


class RedisBackend(RateLimitBackend):
    """Redis-based rate limit backend.
    
    Suitable for multi-instance deployments.
    """
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._redis = None
    
    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as redis
            self._redis = redis.from_url(self.redis_url)
        return self._redis
    
    async def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        try:
            redis = await self._get_redis()
            
            # Use Redis INCR with expiry for sliding window
            now = time.time()
            window_start = now - window
            
            # Key for this rate limit
            redis_key = f"ratelimit:{key}"
            
            # Remove old entries and add new one
            async with redis.pipeline() as pipe:
                # Remove expired entries
                await pipe.zremrangebyscore(redis_key, 0, window_start)
                # Count current entries
                await pipe.zcard(redis_key)
                # Execute
                results = await pipe.execute()
            
            current_count = results[1]
            
            if current_count < limit:
                # Add new entry
                await redis.zadd(redis_key, {str(now): now})
                await redis.expire(redis_key, window)
                return True, limit - current_count - 1
            
            return False, 0
            
        except Exception as e:
            logger.error(f"Redis rate limit error: {e}")
            # Fallback to allowing on Redis error
            return True, limit


# ============================================================================
# RATE LIMITER
# ============================================================================

@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_minute: int = 60
    requests_per_hour: int = 3600
    burst_limit: int = 100


class RateLimiter:
    """Rate limiter with tenant-aware limits."""
    
    # Default limits by plan
    PLAN_LIMITS = {
        "FREE": RateLimitConfig(requests_per_minute=30, burst_limit=50),
        "STARTER": RateLimitConfig(requests_per_minute=60, burst_limit=100),
        "PROFESSIONAL": RateLimitConfig(requests_per_minute=120, burst_limit=200),
        "ENTERPRISE": RateLimitConfig(requests_per_minute=300, burst_limit=500),
    }
    
    def __init__(self, backend: Optional[RateLimitBackend] = None):
        self.backend = backend or self._create_backend()
        self._tenant_limits: Dict[str, RateLimitConfig] = {}
    
    def _create_backend(self) -> RateLimitBackend:
        """Create appropriate backend based on configuration."""
        if REDIS_URL:
            logger.info(f"Using Redis rate limit backend: {REDIS_URL}")
            return RedisBackend(REDIS_URL)
        else:
            logger.info("Using in-memory rate limit backend")
            return InMemoryBackend()
    
    def get_limit_for_tenant(
        self,
        tenant_id: str,
        plan: str,
        custom_limit: Optional[int] = None,
    ) -> RateLimitConfig:
        """Get rate limit config for a tenant."""
        if tenant_id in self._tenant_limits:
            return self._tenant_limits[tenant_id]
        
        # Use custom limit or plan default
        if custom_limit:
            config = RateLimitConfig(requests_per_minute=custom_limit)
        else:
            config = self.PLAN_LIMITS.get(plan, self.PLAN_LIMITS["FREE"])
        
        return config
    
    async def check_rate_limit(
        self,
        tenant_id: str,
        plan: str,
        custom_limit: Optional[int] = None,
    ) -> tuple[bool, dict]:
        """Check if tenant has exceeded rate limit.
        
        Returns:
            Tuple of (is_allowed, info_dict)
        """
        if not RATE_LIMIT_ENABLED:
            return True, {"remaining": -1, "limit": -1}
        
        config = self.get_limit_for_tenant(tenant_id, plan, custom_limit)
        
        # Check per-minute limit
        key = f"{tenant_id}:minute"
        allowed, remaining = await self.backend.is_allowed(
            key,
            config.requests_per_minute,
            60
        )
        
        if not allowed:
            logger.warning(f"Rate limit exceeded for tenant {tenant_id}")
            return False, {
                "remaining": 0,
                "limit": config.requests_per_minute,
                "reset_in": 60,
                "retry_after": 60,
            }
        
        return True, {
            "remaining": remaining,
            "limit": config.requests_per_minute,
        }


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


# ============================================================================
# FASTAPI MIDDLEWARE
# ============================================================================

class RateLimitMiddleware:
    """FastAPI middleware for rate limiting.
    
    Usage:
        @app.middleware("http")
        async def rate_limit_middleware(request: Request, call_next):
            middleware = RateLimitMiddleware()
            return await middleware(request, call_next)
    """
    
    # Exempt paths from rate limiting
    EXEMPT_PATHS = {
        "/health",
        "/api/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
    
    async def __call__(self, request: Request, call_next):
        """Process request and check rate limits."""
        # Skip exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)
        
        # Skip OPTIONS requests
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Get tenant context
        ctx = getattr(request.state, "tenant_context", None)
        if not ctx:
            # No tenant context, skip rate limiting
            return await call_next(request)
        
        # Check rate limit
        limiter = get_rate_limiter()
        allowed, info = await limiter.check_rate_limit(
            tenant_id=ctx.tenant_id,
            plan=ctx.tenant_plan,
            custom_limit=ctx.rate_limit_per_minute,
        )
        
        # Add rate limit headers
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(info.get("limit", 0))
        response.headers["X-RateLimit-Remaining"] = str(info.get("remaining", 0))
        
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "code": "RATE_LIMIT_EXCEEDED",
                    "retry_after": info.get("retry_after", 60),
                },
                headers={
                    "Retry-After": str(info.get("retry_after", 60)),
                    "X-RateLimit-Limit": str(info.get("limit", 0)),
                    "X-RateLimit-Remaining": "0",
                }
            )
        
        return response


# ============================================================================
# DECORATOR FOR SPECIFIC ENDPOINTS
# ============================================================================

def rate_limit(
    requests_per_minute: int = 60,
    key_func: Optional[Callable] = None,
):
    """Decorator for rate limiting specific endpoints.
    
    Usage:
        @router.post("/chat")
        @rate_limit(requests_per_minute=30)
        async def chat_endpoint(request: Request, ...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                return await func(*args, **kwargs)
            
            # Get key
            if key_func:
                key = await key_func(request)
            else:
                ctx = getattr(request.state, "tenant_context", None)
                key = ctx.tenant_id if ctx else "anonymous"
            
            # Check rate limit
            limiter = get_rate_limiter()
            allowed, _ = await limiter.backend.is_allowed(
                f"endpoint:{key}:{func.__name__}",
                requests_per_minute,
                60
            )
            
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded for this endpoint",
                    headers={"Retry-After": "60"}
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator
