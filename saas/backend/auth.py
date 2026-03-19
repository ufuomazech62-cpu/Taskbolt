# -*- coding: utf-8 -*-
"""Firebase Authentication Integration for Multi-Tenant SaaS.

This module handles:
- Firebase Auth token verification
- User synchronization with database
- Tenant context extraction from JWT claims
- Role-based access control

Architecture:
    Firebase Auth (Frontend) → JWT Token → Backend Verification → Tenant Context
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Environment variables
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "")
FIREBASE_CREDENTIALS_PATH = os.environ.get("FIREBASE_CREDENTIALS_PATH", "")

# Initialize Firebase Admin SDK
_firebase_app: Optional[firebase_admin.App] = None


def get_firebase_app() -> firebase_admin.App:
    """Get or initialize Firebase Admin app."""
    global _firebase_app
    
    if _firebase_app is not None:
        return _firebase_app
    
    if FIREBASE_CREDENTIALS_PATH and os.path.exists(FIREBASE_CREDENTIALS_PATH):
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        _firebase_app = firebase_admin.initialize_app(cred)
    elif FIREBASE_PROJECT_ID:
        # Use default credentials (for Cloud Run/Cloud Functions)
        _firebase_app = firebase_admin.initialize_app(options={
            "projectId": FIREBASE_PROJECT_ID,
        })
    else:
        raise RuntimeError(
            "Firebase not configured. Set FIREBASE_PROJECT_ID or "
            "FIREBASE_CREDENTIALS_PATH environment variable."
        )
    
    return _firebase_app


# ============================================================================
# MODELS
# ============================================================================

class UserRole:
    """User role constants."""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"
    
    # Role hierarchy for permission checks
    HIERARCHY = {
        OWNER: 4,
        ADMIN: 3,
        MEMBER: 2,
        VIEWER: 1,
    }


@dataclass
class TenantContext:
    """Tenant context extracted from authenticated user."""
    tenant_id: str
    tenant_slug: str
    tenant_name: str
    tenant_plan: str
    
    user_id: str
    firebase_uid: str
    email: str
    role: str
    permissions: List[str]
    
    # Rate limiting
    rate_limit_per_minute: int
    
    # Feature flags
    features: Dict[str, bool]


class FirebaseToken(BaseModel):
    """Decoded Firebase token payload."""
    uid: str
    email: str
    email_verified: bool = False
    name: Optional[str] = None
    picture: Optional[str] = None
    tenant_id: Optional[str] = None  # Custom claim
    role: Optional[str] = None  # Custom claim
    issued_at: int
    expires_at: int


# ============================================================================
# AUTHENTICATION MIDDLEWARE
# ============================================================================

security = HTTPBearer()


class FirebaseAuthMiddleware:
    """FastAPI middleware for Firebase Authentication.
    
    Usage:
        @app.middleware("http")
        async def firebase_auth_middleware(request: Request, call_next):
            middleware = FirebaseAuthMiddleware()
            return await middleware(request, call_next)
    """
    
    # Public paths that don't require authentication
    PUBLIC_PATHS = {
        "/health",
        "/api/health",
        "/api/auth/status",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
    
    # Static asset prefixes
    PUBLIC_PREFIXES = (
        "/assets/",
        "/static/",
        "/_next/",
    )
    
    async def __call__(self, request: Request, call_next):
        """Process request and verify authentication."""
        # Skip auth for public paths
        if self._is_public_path(request.url.path):
            return await call_next(request)
        
        # Skip OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Extract and verify token
        try:
            token = self._extract_token(request)
            if not token:
                return self._unauthorized_response("Missing authentication token")
            
            # Verify token with Firebase
            decoded = self._verify_token(token)
            if not decoded:
                return self._unauthorized_response("Invalid or expired token")
            
            # Get tenant context
            tenant_ctx = await self._get_tenant_context(decoded)
            if not tenant_ctx:
                return self._unauthorized_response("User not associated with a tenant")
            
            # Attach context to request state
            request.state.tenant_context = tenant_ctx
            request.state.firebase_token = decoded
            request.state.user_id = tenant_ctx.user_id
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Authentication error: {e}", exc_info=True)
            return self._unauthorized_response(str(e))
        
        return await call_next(request)
    
    def _is_public_path(self, path: str) -> bool:
        """Check if path is public (no auth required)."""
        if path in self.PUBLIC_PATHS:
            return True
        return any(path.startswith(p) for p in self.PUBLIC_PREFIXES)
    
    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract Bearer token from request."""
        # Check Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        
        # Check query parameter for WebSocket
        if "upgrade" in request.headers.get("connection", "").lower():
            return request.query_params.get("token")
        
        return None
    
    def _verify_token(self, token: str) -> Optional[FirebaseToken]:
        """Verify Firebase ID token."""
        try:
            app = get_firebase_app()
            decoded = firebase_auth.verify_id_token(token, app=app)
            
            return FirebaseToken(
                uid=decoded["uid"],
                email=decoded.get("email", ""),
                email_verified=decoded.get("email_verified", False),
                name=decoded.get("name"),
                picture=decoded.get("picture"),
                tenant_id=decoded.get("tenant_id"),
                role=decoded.get("role", UserRole.MEMBER),
                issued_at=decoded.get("auth_time", 0),
                expires_at=decoded.get("exp", 0),
            )
        except firebase_auth.ExpiredIdTokenError:
            logger.warning("Firebase token expired")
            return None
        except firebase_auth.InvalidIdTokenError as e:
            logger.warning(f"Invalid Firebase token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token verification error: {e}", exc_info=True)
            return None
    
    async def _get_tenant_context(self, token: FirebaseToken) -> Optional[TenantContext]:
        """Get tenant context from database.
        
        This should be implemented to query your database for:
        - Tenant info
        - User info
        - Permissions
        """
        # Import here to avoid circular dependency
        from .database import get_db
        
        if not token.tenant_id:
            # Try to get tenant_id from database by firebase_uid
            async with get_db() as db:
                user = await db.user.find_unique(
                    where={"firebaseUid": token.uid},
                    include={"tenant": True}
                )
                if not user:
                    return None
                tenant = user.tenant
        else:
            async with get_db() as db:
                user = await db.user.find_first(
                    where={
                        "firebaseUid": token.uid,
                        "tenantId": token.tenant_id,
                    },
                    include={"tenant": True}
                )
                if not user:
                    return None
                tenant = user.tenant
        
        return TenantContext(
            tenant_id=tenant.id,
            tenant_slug=tenant.slug,
            tenant_name=tenant.name,
            tenant_plan=tenant.plan.value,
            user_id=user.id,
            firebase_uid=token.uid,
            email=user.email,
            role=user.role.value,
            permissions=user.permissions if isinstance(user.permissions, list) else [],
            rate_limit_per_minute=tenant.rateLimitPerMinute,
            features=tenant.settings.get("features", {}) if tenant.settings else {},
        )
    
    def _unauthorized_response(self, message: str):
        """Return 401 Unauthorized response."""
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=401,
            content={"detail": message, "code": "UNAUTHORIZED"},
        )


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

async def get_tenant_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TenantContext:
    """FastAPI dependency to get tenant context.
    
    Usage:
        @router.get("/agents")
        async def list_agents(ctx: TenantContext = Depends(get_tenant_context)):
            return {"tenant_id": ctx.tenant_id}
    """
    ctx = getattr(request.state, "tenant_context", None)
    if not ctx:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return ctx


async def get_optional_tenant_context(
    request: Request,
) -> Optional[TenantContext]:
    """FastAPI dependency for optional authentication."""
    return getattr(request.state, "tenant_context", None)


def require_role(*required_roles: str):
    """Decorator to require specific roles.
    
    Usage:
        @router.delete("/agents/{agent_id}")
        async def delete_agent(
            agent_id: str,
            ctx: TenantContext = Depends(require_role(UserRole.ADMIN, UserRole.OWNER))
        ):
            ...
    """
    async def role_checker(
        ctx: TenantContext = Depends(get_tenant_context)
    ) -> TenantContext:
        user_level = UserRole.HIERARCHY.get(ctx.role, 0)
        required_level = max(UserRole.HIERARCHY.get(r, 0) for r in required_roles)
        
        if user_level < required_level:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions",
                code="FORBIDDEN",
            )
        return ctx
    
    return role_checker


# ============================================================================
# USER SYNCHRONIZATION
# ============================================================================

async def sync_user_from_firebase(
    firebase_uid: str,
    email: str,
    display_name: Optional[str] = None,
    photo_url: Optional[str] = None,
) -> Optional[str]:
    """Sync user from Firebase Auth to database.
    
    Called when:
    - New user signs up
    - User logs in and doesn't exist locally
    
    Returns:
        User ID if successful, None otherwise
    """
    from .database import get_db
    
    async with get_db() as db:
        # Check if user exists
        existing_user = await db.user.find_unique(
            where={"firebaseUid": firebase_uid}
        )
        
        if existing_user:
            # Update last login
            await db.user.update(
                where={"id": existing_user.id},
                data={
                    "lastLoginAt": datetime.utcnow(),
                    "displayName": display_name or existing_user.displayName,
                    "avatarUrl": photo_url or existing_user.avatarUrl,
                }
            )
            return existing_user.id
        
        # For new users, we need a tenant
        # This could be:
        # 1. Auto-create a tenant for the user
        # 2. Require invitation
        # 3. Use a default tenant
        
        logger.info(f"New Firebase user not found in database: {firebase_uid}")
        return None


async def set_custom_claims(
    firebase_uid: str,
    tenant_id: str,
    role: str = UserRole.MEMBER,
) -> None:
    """Set custom claims on Firebase user for tenant context.
    
    This allows the tenant_id to be included in the JWT token.
    """
    app = get_firebase_app()
    firebase_auth.set_custom_user_claims(
        firebase_uid,
        {
            "tenant_id": tenant_id,
            "role": role,
        },
        app=app,
    )
    logger.info(f"Set custom claims for user {firebase_uid}: tenant={tenant_id}, role={role}")


# ============================================================================
# API KEY AUTHENTICATION (Alternative to Firebase Auth)
# ============================================================================

import hashlib
import secrets


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key.
    
    Returns:
        Tuple of (raw_key, key_hash)
        raw_key should be shown to user ONCE
        key_hash should be stored in database
    """
    raw_key = f"cpk_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    return raw_key, key_hash


def verify_api_key(raw_key: str) -> Optional[str]:
    """Verify API key and return key prefix for lookup.
    
    Returns:
        Key prefix for database lookup
    """
    if not raw_key.startswith("cpk_"):
        return None
    return raw_key[:12]  # cpk_xxxxxxxx


async def authenticate_api_key(
    api_key: str,
) -> Optional[TenantContext]:
    """Authenticate using API key.
    
    Used for programmatic access (CLI, integrations).
    """
    from .database import get_db
    
    key_prefix = verify_api_key(api_key)
    if not key_prefix:
        return None
    
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    async with get_db() as db:
        api_key_record = await db.apiKey.find_unique(
            where={"keyHash": key_hash},
            include={"tenant": True}
        )
        
        if not api_key_record or not api_key_record.isActive:
            return None
        
        if api_key_record.expiresAt and api_key_record.expiresAt < datetime.utcnow():
            return None
        
        # Update last used
        await db.apiKey.update(
            where={"id": api_key_record.id},
            data={"lastUsedAt": datetime.utcnow()}
        )
        
        tenant = api_key_record.tenant
        
        return TenantContext(
            tenant_id=tenant.id,
            tenant_slug=tenant.slug,
            tenant_name=tenant.name,
            tenant_plan=tenant.plan.value,
            user_id=None,  # API key, not user
            firebase_uid=None,
            email=None,
            role="api_key",
            permissions=api_key_record.scopes if isinstance(api_key_record.scopes, list) else [],
            rate_limit_per_minute=api_key_record.rateLimitPerMinute or tenant.rateLimitPerMinute,
            features=tenant.settings.get("features", {}) if tenant.settings else {},
        )
