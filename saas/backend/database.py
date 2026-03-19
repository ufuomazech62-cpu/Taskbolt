# -*- coding: utf-8 -*-
"""Database Connection and Session Management for Multi-Tenant SaaS.

Uses Prisma ORM with connection pooling for Google Cloud SQL (PostgreSQL).

Features:
- Async database operations
- Connection pooling
- Automatic tenant isolation in queries
- Transaction support
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator, TypeVar, Callable, Any
from functools import wraps

from prisma import Prisma
from prisma.types import WhereInput

logger = logging.getLogger(__name__)

# Environment configuration
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/taskbolt_saas?schema=public"
)

# Connection pool settings
DATABASE_POOL_SIZE = int(os.environ.get("DATABASE_POOL_SIZE", "10"))
DATABASE_MAX_OVERFLOW = int(os.environ.get("DATABASE_MAX_OVERFLOW", "20"))

# Global Prisma client
_db_client: Optional[Prisma] = None


async def init_db() -> None:
    """Initialize database connection pool.
    
    Should be called during application startup.
    """
    global _db_client
    
    if _db_client is not None:
        return
    
    _db_client = Prisma()
    await _db_client.connect()
    logger.info(f"Database connected: {DATABASE_URL.split('@')[-1]}")


async def close_db() -> None:
    """Close database connection pool.
    
    Should be called during application shutdown.
    """
    global _db_client
    
    if _db_client is not None:
        await _db_client.disconnect()
        _db_client = None
        logger.info("Database connection closed")


def get_db() -> Prisma:
    """Get the Prisma client instance.
    
    For use in dependency injection and direct access.
    """
    global _db_client
    
    if _db_client is None:
        raise RuntimeError(
            "Database not initialized. Call init_db() during startup."
        )
    
    return _db_client


@asynccontextmanager
async def db_session() -> AsyncGenerator[Prisma, None]:
    """Async context manager for database sessions.
    
    Usage:
        async with db_session() as db:
            users = await db.user.find_many()
    """
    db = get_db()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {e}", exc_info=True)
        raise


# ============================================================================
# TENANT-SCOPED QUERIES
# ============================================================================

def tenant_scope(tenant_id: str) -> WhereInput:
    """Create a tenant-scoped where clause.
    
    Usage:
        agents = await db.agent.find_many(
            where=tenant_scope(tenant_id)
        )
    """
    return {"tenantId": tenant_id}


class TenantQuery:
    """Helper class for building tenant-scoped queries.
    
    Usage:
        query = TenantQuery(tenant_id)
        
        # Find all agents
        agents = await query.find_many(db.agent)
        
        # Find with conditions
        agents = await query.find_many(
            db.agent,
            where={"isActive": True}
        )
    """
    
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
    
    def _add_tenant_filter(self, where: Optional[WhereInput] = None) -> WhereInput:
        """Add tenant filter to where clause."""
        if where is None:
            return {"tenantId": self.tenant_id}
        
        if isinstance(where, dict):
            return {**where, "tenantId": self.tenant_id}
        
        return where
    
    async def find_many(
        self,
        model: Any,
        where: Optional[WhereInput] = None,
        **kwargs
    ):
        """Find many records with tenant filter."""
        return await model.find_many(
            where=self._add_tenant_filter(where),
            **kwargs
        )
    
    async def find_unique(
        self,
        model: Any,
        where: WhereInput,
    ):
        """Find unique record with tenant validation."""
        # For unique queries, we need to include tenant_id
        record = await model.find_unique(where=where)
        
        if record and hasattr(record, 'tenantId'):
            if record.tenantId != self.tenant_id:
                return None
        
        return record
    
    async def find_first(
        self,
        model: Any,
        where: Optional[WhereInput] = None,
        **kwargs
    ):
        """Find first record with tenant filter."""
        return await model.find_first(
            where=self._add_tenant_filter(where),
            **kwargs
        )
    
    async def create(
        self,
        model: Any,
        data: dict,
    ):
        """Create record with tenant_id automatically set."""
        data["tenantId"] = self.tenant_id
        return await model.create(data=data)
    
    async def update(
        self,
        model: Any,
        where: WhereInput,
        data: dict,
    ):
        """Update record with tenant validation."""
        # First verify the record belongs to tenant
        record = await self.find_unique(model, where)
        if not record:
            return None
        
        return await model.update(
            where=where,
            data=data
        )
    
    async def delete(
        self,
        model: Any,
        where: WhereInput,
    ):
        """Delete record with tenant validation."""
        # First verify the record belongs to tenant
        record = await self.find_unique(model, where)
        if not record:
            return None
        
        return await model.delete(where=where)
    
    async def count(
        self,
        model: Any,
        where: Optional[WhereInput] = None,
    ) -> int:
        """Count records with tenant filter."""
        return await model.count(
            where=self._add_tenant_filter(where)
        )


# ============================================================================
# AUDIT LOGGING
# ============================================================================

async def log_audit(
    tenant_id: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    user_id: Optional[str] = None,
    old_values: Optional[dict] = None,
    new_values: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Log an audit event.
    
    Usage:
        await log_audit(
            tenant_id=ctx.tenant_id,
            action="agent.created",
            resource_type="agent",
            resource_id=agent.id,
            user_id=ctx.user_id,
            new_values={"name": agent.name},
            request=request,
        )
    """
    db = get_db()
    
    await db.auditlog.create(
        data={
            "tenantId": tenant_id,
            "userId": user_id,
            "action": action,
            "resourceType": resource_type,
            "resourceId": resource_id,
            "oldValues": old_values,
            "newValues": new_values,
            "ipAddress": ip_address,
            "userAgent": user_agent,
        }
    )
    
    logger.debug(
        f"Audit: {action} on {resource_type}/{resource_id} "
        f"by user/{user_id} in tenant/{tenant_id}"
    )


# ============================================================================
# USAGE TRACKING
# ============================================================================

async def track_usage(
    tenant_id: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    agent_id: Optional[str] = None,
    model_provider: Optional[str] = None,
    model_name: Optional[str] = None,
    estimated_cost_cents: int = 0,
) -> None:
    """Track token usage for billing.
    
    Usage:
        await track_usage(
            tenant_id=ctx.tenant_id,
            input_tokens=100,
            output_tokens=50,
            agent_id=agent.id,
            model_provider="openai",
            model_name="gpt-4",
        )
    """
    db = get_db()
    
    await db.usagerecord.create(
        data={
            "tenantId": tenant_id,
            "agentId": agent_id,
            "modelProvider": model_provider,
            "modelName": model_name,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "totalTokens": input_tokens + output_tokens,
            "estimatedCostCents": estimated_cost_cents,
        }
    )


async def get_usage_summary(
    tenant_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """Get usage summary for a tenant."""
    db = get_db()
    
    where = {"tenantId": tenant_id}
    
    if start_date or end_date:
        where["createdAt"] = {}
        if start_date:
            where["createdAt"]["gte"] = start_date
        if end_date:
            where["createdAt"]["lte"] = end_date
    
    records = await db.usagerecord.find_many(where=where)
    
    total_input = sum(r.inputTokens for r in records)
    total_output = sum(r.outputTokens for r in records)
    total_cost = sum(r.estimatedCostCents for r in records)
    
    return {
        "total_records": len(records),
        "input_tokens": total_input,
        "output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "estimated_cost_cents": total_cost,
        "estimated_cost_dollars": total_cost / 100,
    }


# ============================================================================
# DATABASE HEALTH CHECK
# ============================================================================

async def health_check() -> dict:
    """Check database health."""
    try:
        db = get_db()
        
        # Simple query to test connection
        await db.$query_raw`SELECT 1`
        
        return {
            "status": "healthy",
            "database": "connected",
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
        }
