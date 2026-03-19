# -*- coding: utf-8 -*-
"""Taskbolt SaaS - Multi-Tenant FastAPI Application.

Main application with:
- Firebase Authentication
- Tenant Isolation
- Rate Limiting
- Audit Logging
- Multi-Agent Support
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .auth import (
    FirebaseAuthMiddleware,
    init_firebase,
    get_tenant_context,
    TenantContext,
)
from .database import init_db, close_db, health_check, log_audit
from .rate_limit import RateLimitMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Environment configuration
TASKBOLT_PORT = int(os.environ.get("TASKBOLT_PORT", "8088"))
CORS_ORIGINS = os.environ.get("TASKBOLT_CORS_ORIGINS", "")
DEBUG = os.environ.get("TASKBOLT_DEBUG", "false").lower() == "true"


# ============================================================================
# APPLICATION LIFESPAN
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    logger.info("Starting Taskbolt SaaS application...")
    
    # Initialize Firebase Auth
    try:
        init_firebase()
        logger.info("Firebase Auth initialized")
    except Exception as e:
        logger.warning(f"Firebase initialization skipped: {e}")
    
    # Initialize database
    await init_db()
    
    # Startup complete
    logger.info("Taskbolt SaaS application started")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Taskbolt SaaS application...")
    await close_db()
    logger.info("Taskbolt SaaS application stopped")


# ============================================================================
# CREATE APPLICATION
# ============================================================================

app = FastAPI(
    title="Taskbolt SaaS",
    description="Multi-tenant AI assistant platform",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    openapi_url="/openapi.json" if DEBUG else None,
)


# ============================================================================
# MIDDLEWARE
# ============================================================================

# CORS middleware
if CORS_ORIGINS:
    origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ============================================================================
# HEALTH CHECK ENDPOINTS
# ============================================================================

@app.get("/health")
@app.get("/api/health")
async def health():
    """Health check endpoint."""
    db_health = await health_check()
    return {
        "status": "ok",
        "version": "2.0.0",
        "database": db_health,
    }


@app.get("/api/version")
async def version():
    """Return API version."""
    return {"version": "2.0.0", "type": "saas"}


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.get("/api/auth/status")
async def auth_status():
    """Check authentication status."""
    return {
        "enabled": True,
        "provider": "firebase",
    }


@app.get("/api/auth/me")
async def get_current_user(ctx: TenantContext = Depends(get_tenant_context)):
    """Get current authenticated user."""
    return {
        "user_id": ctx.user_id,
        "email": ctx.email,
        "role": ctx.role,
        "tenant": {
            "id": ctx.tenant_id,
            "slug": ctx.tenant_slug,
            "name": ctx.tenant_name,
            "plan": ctx.tenant_plan,
        },
    }


# ============================================================================
# TENANT ROUTES
# ============================================================================

@app.get("/api/tenant")
async def get_tenant(ctx: TenantContext = Depends(get_tenant_context)):
    """Get current tenant info."""
    from .database import get_db
    
    db = get_db()
    tenant = await db.tenant.find_unique(
        where={"id": ctx.tenant_id},
        include={
            "users": {"where": {"isActive": True}},
            "agents": {"where": {"isActive": True}},
        }
    )
    
    return {
        "id": tenant.id,
        "slug": tenant.slug,
        "name": tenant.name,
        "plan": tenant.plan.value,
        "limits": {
            "max_agents": tenant.maxAgents,
            "max_users": tenant.maxUsers,
            "max_storage_bytes": tenant.maxStorageBytes,
        },
        "stats": {
            "users_count": len(tenant.users),
            "agents_count": len(tenant.agents),
        },
    }


# ============================================================================
# AGENT ROUTES
# ============================================================================

@app.get("/api/agents")
async def list_agents(ctx: TenantContext = Depends(get_tenant_context)):
    """List all agents for the current tenant."""
    from .database import get_db, TenantQuery
    
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    agents = await query.find_many(
        db.agent,
        where={"isActive": True},
        order={"createdAt": "desc"}
    )
    
    return {
        "agents": [
            {
                "id": agent.id,
                "external_id": agent.externalId,
                "name": agent.name,
                "description": agent.description,
                "is_active": agent.isActive,
                "created_at": agent.createdAt.isoformat(),
            }
            for agent in agents
        ]
    }


@app.get("/api/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Get a specific agent."""
    from .database import get_db, TenantQuery
    
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    agent = await query.find_unique(db.agent, {"id": agent_id})
    
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return {
        "id": agent.id,
        "external_id": agent.externalId,
        "name": agent.name,
        "description": agent.description,
        "channels": agent.channels,
        "mcp": agent.mcp,
        "tools": agent.tools,
        "security": agent.security,
        "running": agent.running,
        "llm_routing": agent.llmRouting,
        "is_active": agent.isActive,
        "created_at": agent.createdAt.isoformat(),
        "updated_at": agent.updatedAt.isoformat(),
    }


@app.post("/api/agents")
async def create_agent(
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Create a new agent."""
    from .database import get_db, TenantQuery
    from .auth import require_role, UserRole
    
    # Check permissions
    if UserRole.HIERARCHY.get(ctx.role, 0) < UserRole.HIERARCHY[UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    # Check agent limit
    current_count = await query.count(db.agent)
    tenant = await db.tenant.find_unique(where={"id": ctx.tenant_id})
    
    if current_count >= tenant.maxAgents:
        raise HTTPException(
            status_code=403,
            detail=f"Agent limit reached ({tenant.maxAgents}). Upgrade your plan."
        )
    
    # Parse request body
    body = await request.json()
    
    # Create agent
    agent = await query.create(db.agent, {
        "externalId": body.get("external_id", f"agent_{current_count + 1}"),
        "name": body.get("name", "New Agent"),
        "description": body.get("description", ""),
        "channels": body.get("channels", {}),
        "mcp": body.get("mcp", {}),
        "tools": body.get("tools", {}),
        "security": body.get("security", {}),
        "running": body.get("running", {}),
        "llmRouting": body.get("llm_routing", {}),
    })
    
    # Log audit
    await log_audit(
        tenant_id=ctx.tenant_id,
        action="agent.created",
        resource_type="agent",
        resource_id=agent.id,
        user_id=ctx.user_id,
        new_values={"name": agent.name, "external_id": agent.externalId},
    )
    
    return {
        "id": agent.id,
        "external_id": agent.externalId,
        "name": agent.name,
    }


# ============================================================================
# CHAT ROUTES
# ============================================================================

@app.get("/api/agents/{agent_id}/chats")
async def list_chats(
    agent_id: str,
    ctx: TenantContext = Depends(get_tenant_context)
):
    """List chats for an agent."""
    from .database import get_db, TenantQuery
    
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    # Verify agent exists and belongs to tenant
    agent = await query.find_unique(db.agent, {"id": agent_id})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    chats = await db.chat.find_many(
        where={
            "tenantId": ctx.tenant_id,
            "agentId": agent_id,
            "userId": ctx.user_id,
        },
        order={"updatedAt": "desc"},
        take=50,
    )
    
    return {
        "chats": [
            {
                "id": chat.id,
                "external_id": chat.externalId,
                "name": chat.name,
                "status": chat.status.value,
                "created_at": chat.createdAt.isoformat(),
                "updated_at": chat.updatedAt.isoformat(),
            }
            for chat in chats
        ]
    }


# ============================================================================
# API KEY ROUTES
# ============================================================================

@app.get("/api/api-keys")
async def list_api_keys(ctx: TenantContext = Depends(get_tenant_context)):
    """List API keys for the current tenant."""
    from .database import get_db, TenantQuery
    
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    keys = await query.find_many(
        db.apiKey,
        where={"isActive": True},
        order={"createdAt": "desc"}
    )
    
    return {
        "api_keys": [
            {
                "id": key.id,
                "name": key.name,
                "key_prefix": key.keyPrefix,
                "scopes": key.scopes,
                "last_used_at": key.lastUsedAt.isoformat() if key.lastUsedAt else None,
                "created_at": key.createdAt.isoformat(),
            }
            for key in keys
        ]
    }


@app.post("/api/api-keys")
async def create_api_key(
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Create a new API key."""
    from .database import get_db, TenantQuery
    from .auth import generate_api_key, require_role, UserRole
    
    # Check permissions
    if UserRole.HIERARCHY.get(ctx.role, 0) < UserRole.HIERARCHY[UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    body = await request.json()
    
    # Generate API key
    raw_key, key_hash = generate_api_key()
    key_prefix = raw_key[:12]
    
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    api_key = await query.create(db.apiKey, {
        "name": body.get("name", "API Key"),
        "keyHash": key_hash,
        "keyPrefix": key_prefix,
        "scopes": body.get("scopes", ["read", "write"]),
    })
    
    # Log audit
    await log_audit(
        tenant_id=ctx.tenant_id,
        action="api_key.created",
        resource_type="api_key",
        resource_id=api_key.id,
        user_id=ctx.user_id,
        new_values={"name": api_key.name},
    )
    
    # Return the raw key ONCE
    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": raw_key,  # Only shown once!
        "key_prefix": key_prefix,
        "warning": "Store this key securely. It will not be shown again.",
    }


@app.delete("/api/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Revoke an API key."""
    from .database import get_db, TenantQuery
    
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    # Find and delete the key
    api_key = await query.delete(db.apiKey, {"id": key_id})
    
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    
    await log_audit(
        tenant_id=ctx.tenant_id,
        action="api_key.revoked",
        resource_type="api_key",
        resource_id=key_id,
        user_id=ctx.user_id,
    )
    
    return {"success": True}


# ============================================================================
# USAGE ROUTES
# ============================================================================

@app.get("/api/usage")
async def get_usage(ctx: TenantContext = Depends(get_tenant_context)):
    """Get usage statistics for the current tenant."""
    from .database import get_usage_summary
    
    summary = await get_usage_summary(ctx.tenant_id)
    
    return {
        "tenant_id": ctx.tenant_id,
        **summary
    }


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "code": getattr(exc, "code", "HTTP_ERROR"),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "code": "INTERNAL_ERROR",
        },
    )


# ============================================================================
# STATIC FILES (Frontend)
# ============================================================================

# This will be configured to serve the React frontend
# The frontend will be built separately and served by FastAPI

STATIC_DIR = os.environ.get("TASKBOLT_FRONTEND_DIR", "/app/frontend/dist")

if Path(STATIC_DIR).exists():
    app.mount("/assets", StaticFiles(directory=f"{STATIC_DIR}/assets"), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the SPA for all unmatched routes."""
        index_path = Path(STATIC_DIR) / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"error": "Frontend not built"}


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "taskbolt.saas.backend.app:app",
        host="0.0.0.0",
        port=TASKBOLT_PORT,
        reload=DEBUG,
    )
