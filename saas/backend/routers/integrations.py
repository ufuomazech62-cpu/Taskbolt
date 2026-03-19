# -*- coding: utf-8 -*-
"""
Taskbolt SaaS - Integrations API

Provides endpoints for third-party service integrations:
- Slack integration
- Discord bot management
- Microsoft Teams
- Zapier/Make webhooks
- Custom integrations with OAuth
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import urllib.parse
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ..auth import TenantContext, get_tenant_context, require_role
from ..database import get_db, TenantQuery, log_audit
from ..rate_limit import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])

# Configuration
OAUTH_STATE_SECRET = os.environ.get("OAUTH_STATE_SECRET", secrets.token_hex(32))


# ============================================================================
# MODELS
# ============================================================================

class IntegrationConfig(BaseModel):
    """Integration configuration."""
    type: str
    name: str
    enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict)
    credentials: Dict[str, str] = Field(default_factory=dict)


class SlackIntegrationCreate(BaseModel):
    """Request to create Slack integration."""
    name: str = "Slack"
    bot_token: str
    app_token: Optional[str] = None
    signing_secret: Optional[str] = None
    channels: List[str] = Field(default_factory=list)


class DiscordIntegrationCreate(BaseModel):
    """Request to create Discord integration."""
    name: str = "Discord"
    bot_token: str
    application_id: Optional[str] = None
    guild_id: Optional[str] = None
    channels: List[str] = Field(default_factory=list)


class TeamsIntegrationCreate(BaseModel):
    """Request to create Microsoft Teams integration."""
    name: str = "Microsoft Teams"
    tenant_id: str
    client_id: str
    client_secret: str
    channels: List[str] = Field(default_factory=list)


class ZapierIntegrationCreate(BaseModel):
    """Request to create Zapier integration."""
    name: str = "Zapier"
    webhook_url: str
    events: List[str] = Field(default_factory=lambda: ["chat.message", "agent.task_completed"])


# ============================================================================
# INTEGRATIONS LIST
# ============================================================================

SUPPORTED_INTEGRATIONS = [
    {
        "type": "slack",
        "name": "Slack",
        "description": "Send and receive messages in Slack channels",
        "icon": "slack",
        "features": ["双向消息", "Slash 命令", "交互式组件"],
        "oauth_supported": True,
    },
    {
        "type": "discord",
        "name": "Discord",
        "description": "Connect your Discord server to Taskbolt",
        "icon": "discord",
        "features": ["Bot 集成", "频道消息", "Slash 命令"],
        "oauth_supported": True,
    },
    {
        "type": "teams",
        "name": "Microsoft Teams",
        "description": "Integrate with Microsoft Teams",
        "icon": "teams",
        "features": ["Bot 框架", "自适应卡片", "Teams 频道"],
        "oauth_supported": True,
    },
    {
        "type": "zapier",
        "name": "Zapier",
        "description": "Connect to 5000+ apps via Zapier",
        "icon": "zapier",
        "features": ["Webhooks", "自动化工作流"],
        "oauth_supported": False,
    },
    {
        "type": "make",
        "name": "Make (Integromat)",
        "description": "Connect via Make automation platform",
        "icon": "make",
        "features": ["Webhooks", "场景自动化"],
        "oauth_supported": False,
    },
    {
        "type": "custom",
        "name": "Custom Integration",
        "description": "Build your own integration with webhooks",
        "icon": "code",
        "features": ["Webhook 接收", "API 访问"],
        "oauth_supported": False,
    },
]


@router.get("")
async def list_available_integrations():
    """List all available integrations."""
    return {"integrations": SUPPORTED_INTEGRATIONS}


@router.get("/installed")
async def list_installed_integrations(
    ctx: TenantContext = Depends(get_tenant_context)
):
    """List installed integrations for the tenant."""
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    # Query integrations from database
    integrations = await db.integration.find_many(
        where={"tenantId": ctx.tenant_id},
        order={"createdAt": "desc"},
    )
    
    return {
        "integrations": [
            {
                "id": integ.id,
                "type": integ.type,
                "name": integ.name,
                "enabled": integ.enabled,
                "created_at": integ.createdAt.isoformat(),
                "last_used": integ.lastUsedAt.isoformat() if integ.lastUsedAt else None,
            }
            for integ in integrations
        ]
    }


# ============================================================================
# SLACK INTEGRATION
# ============================================================================

@router.post("/slack")
async def create_slack_integration(
    request: Request,
    ctx: TenantContext = Depends(require_role("admin")),
):
    """Create Slack integration."""
    db = get_db()
    body = await request.json()
    
    # Validate bot token format
    bot_token = body.get("bot_token", "")
    if not bot_token.startswith("xoxb-"):
        raise HTTPException(status_code=400, detail="Invalid Slack bot token format")
    
    # Encrypt sensitive credentials (in production, use proper encryption)
    credentials = {
        "bot_token": _encrypt_credential(bot_token),
        "app_token": _encrypt_credential(body.get("app_token", "")),
        "signing_secret": _encrypt_credential(body.get("signing_secret", "")),
    }
    
    integration = await db.integration.create(
        data={
            "tenantId": ctx.tenant_id,
            "type": "slack",
            "name": body.get("name", "Slack"),
            "config": {
                "channels": body.get("channels", []),
            },
            "credentials": credentials,
        }
    )
    
    await log_audit(
        tenant_id=ctx.tenant_id,
        action="integration.created",
        resource_type="integration",
        resource_id=integration.id,
        user_id=ctx.user_id,
        new_values={"type": "slack", "name": integration.name},
    )
    
    return {
        "id": integration.id,
        "type": "slack",
        "name": integration.name,
        "message": "Slack integration created. Add the bot to your workspace to start.",
    }


@router.get("/slack/oauth")
async def slack_oauth_start(
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Start Slack OAuth flow."""
    client_id = os.environ.get("SLACK_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="Slack OAuth not configured")
    
    # Generate state token
    state = _generate_oauth_state(ctx.tenant_id, "slack")
    
    # Build OAuth URL
    redirect_uri = f"{request.base_url}api/integrations/slack/oauth/callback"
    oauth_url = (
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={client_id}"
        f"&scope=bot,chat:write,channels:read,groups:read,im:read"
        f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
        f"&state={state}"
    )
    
    return {"oauth_url": oauth_url}


@router.get("/slack/oauth/callback")
async def slack_oauth_callback(
    code: str,
    state: str,
):
    """Handle Slack OAuth callback."""
    import httpx
    
    # Verify state
    tenant_id, integration_type = _verify_oauth_state(state)
    if not tenant_id or integration_type != "slack":
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    
    # Exchange code for tokens
    client_id = os.environ.get("SLACK_CLIENT_ID")
    client_secret = os.environ.get("SLACK_CLIENT_SECRET")
    redirect_uri = f"https://api.taskbolt.ai/api/integrations/slack/oauth/callback"
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            }
        )
    
    data = response.json()
    
    if not data.get("ok"):
        raise HTTPException(status_code=400, detail=f"Slack OAuth failed: {data.get('error')}")
    
    # Store integration
    db = get_db()
    integration = await db.integration.create(
        data={
            "tenantId": tenant_id,
            "type": "slack",
            "name": data.get("team", {}).get("name", "Slack"),
            "config": {
                "team_id": data.get("team", {}).get("id"),
                "team_name": data.get("team", {}).get("name"),
                "bot_user_id": data.get("bot_user_id"),
            },
            "credentials": {
                "bot_token": _encrypt_credential(data.get("access_token", "")),
            },
        }
    )
    
    # Redirect to success page
    return RedirectResponse(url="/settings/integrations?success=slack")


# ============================================================================
# DISCORD INTEGRATION
# ============================================================================

@router.post("/discord")
async def create_discord_integration(
    request: Request,
    ctx: TenantContext = Depends(require_role("admin")),
):
    """Create Discord integration."""
    db = get_db()
    body = await request.json()
    
    bot_token = body.get("bot_token", "")
    if not bot_token:
        raise HTTPException(status_code=400, detail="Discord bot token is required")
    
    integration = await db.integration.create(
        data={
            "tenantId": ctx.tenant_id,
            "type": "discord",
            "name": body.get("name", "Discord"),
            "config": {
                "guild_id": body.get("guild_id"),
                "channels": body.get("channels", []),
                "application_id": body.get("application_id"),
            },
            "credentials": {
                "bot_token": _encrypt_credential(bot_token),
            },
        }
    )
    
    await log_audit(
        tenant_id=ctx.tenant_id,
        action="integration.created",
        resource_type="integration",
        resource_id=integration.id,
        user_id=ctx.user_id,
        new_values={"type": "discord", "name": integration.name},
    )
    
    return {
        "id": integration.id,
        "type": "discord",
        "name": integration.name,
        "message": "Discord integration created. Invite the bot to your server.",
    }


# ============================================================================
# ZAPIER / MAKE INTEGRATION
# ============================================================================

@router.post("/zapier")
@rate_limit(requests_per_minute=10)
async def create_zapier_integration(
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Create Zapier integration (webhook)."""
    db = get_db()
    body = await request.json()
    
    webhook_url = body.get("webhook_url", "")
    if not webhook_url:
        raise HTTPException(status_code=400, detail="Webhook URL is required")
    
    integration = await db.integration.create(
        data={
            "tenantId": ctx.tenant_id,
            "type": "zapier",
            "name": body.get("name", "Zapier"),
            "config": {
                "webhook_url": webhook_url,
                "events": body.get("events", ["chat.message"]),
            },
        }
    )
    
    return {
        "id": integration.id,
        "type": "zapier",
        "name": integration.name,
        "webhook_url": webhook_url,
    }


# ============================================================================
# INTEGRATION MANAGEMENT
# ============================================================================

@router.get("/{integration_id}")
async def get_integration(
    integration_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get integration details."""
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    integration = await query.find_unique(db.integration, {"id": integration_id})
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    # Get integration type info
    type_info = next(
        (i for i in SUPPORTED_INTEGRATIONS if i["type"] == integration.type),
        None
    )
    
    return {
        "id": integration.id,
        "type": integration.type,
        "type_info": type_info,
        "name": integration.name,
        "enabled": integration.enabled,
        "config": integration.config,
        "created_at": integration.createdAt.isoformat(),
        "last_used": integration.lastUsedAt.isoformat() if integration.lastUsedAt else None,
    }


@router.patch("/{integration_id}")
async def update_integration(
    integration_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_role("admin")),
):
    """Update integration configuration."""
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    integration = await query.find_unique(db.integration, {"id": integration_id})
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    body = await request.json()
    update_data = {}
    
    if "name" in body:
        update_data["name"] = body["name"]
    if "enabled" in body:
        update_data["enabled"] = body["enabled"]
    if "config" in body:
        update_data["config"] = body["config"]
    
    updated = await db.integration.update(
        where={"id": integration_id},
        data=update_data,
    )
    
    return {
        "id": updated.id,
        "type": updated.type,
        "name": updated.name,
        "enabled": updated.enabled,
    }


@router.delete("/{integration_id}")
async def delete_integration(
    integration_id: str,
    ctx: TenantContext = Depends(require_role("admin")),
):
    """Delete integration."""
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    integration = await query.delete(db.integration, {"id": integration_id})
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    await log_audit(
        tenant_id=ctx.tenant_id,
        action="integration.deleted",
        resource_type="integration",
        resource_id=integration_id,
        user_id=ctx.user_id,
    )
    
    return {"success": True}


@router.post("/{integration_id}/test")
async def test_integration(
    integration_id: str,
    background_tasks: BackgroundTasks,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Test integration connectivity."""
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    integration = await query.find_unique(db.integration, {"id": integration_id})
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    # Queue test in background
    background_tasks.add_task(
        _test_integration_connection,
        integration.id,
        integration.type,
        integration.config,
        integration.credentials,
    )
    
    return {"status": "testing", "integration_id": integration_id}


# ============================================================================
# INCOMING WEBHOOKS (for custom integrations)
# ============================================================================

@router.post("/incoming/{integration_id}")
async def handle_incoming_webhook(
    integration_id: str,
    request: Request,
):
    """Handle incoming webhook from external service."""
    db = get_db()
    
    integration = await db.integration.find_unique(
        where={"id": integration_id},
        include={"tenant": True},
    )
    
    if not integration or not integration.enabled:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    # Verify webhook signature if configured
    secret = integration.config.get("webhook_secret")
    if secret:
        signature = request.headers.get("X-Webhook-Signature", "")
        body = await request.body()
        expected = _compute_webhook_signature(body, secret)
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Parse webhook payload
    try:
        payload = await request.json()
    except:
        payload = {"raw": (await request.body()).decode()}
    
    # Update last used
    await db.integration.update(
        where={"id": integration_id},
        data={"lastUsedAt": datetime.utcnow()},
    )
    
    # Process webhook (this would trigger agent action)
    # TODO: Queue for processing by agent
    
    return {"success": True, "received": payload}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _encrypt_credential(plaintext: str) -> str:
    """Encrypt credential for storage.
    
    In production, use proper encryption (AWS KMS, GCP KMS, etc.)
    This is a placeholder implementation.
    """
    if not plaintext:
        return ""
    # Simple base64 encoding (NOT secure, replace with proper encryption)
    return base64.b64encode(plaintext.encode()).decode()


def _decrypt_credential(encrypted: str) -> str:
    """Decrypt credential."""
    if not encrypted:
        return ""
    return base64.b64decode(encrypted.encode()).decode()


def _generate_oauth_state(tenant_id: str, integration_type: str) -> str:
    """Generate OAuth state token."""
    import hmac
    payload = f"{tenant_id}:{integration_type}:{datetime.utcnow().isoformat()}"
    signature = hmac.new(
        OAUTH_STATE_SECRET.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    return base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()


def _verify_oauth_state(state: str) -> tuple[Optional[str], Optional[str]]:
    """Verify OAuth state and extract tenant_id."""
    import hmac
    try:
        decoded = base64.urlsafe_b64decode(state.encode()).decode()
        parts = decoded.split(":")
        if len(parts) < 4:
            return None, None
        
        tenant_id = parts[0]
        integration_type = parts[1]
        signature = parts[3]
        
        # Verify signature
        payload = ":".join(parts[:3])
        expected = hmac.new(
            OAUTH_STATE_SECRET.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()[:16]
        
        if not hmac.compare_digest(signature, expected):
            return None, None
        
        return tenant_id, integration_type
    except:
        return None, None


def _compute_webhook_signature(body: bytes, secret: str) -> str:
    """Compute webhook signature."""
    import hmac
    return hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()


async def _test_integration_connection(
    integration_id: str,
    integration_type: str,
    config: dict,
    credentials: dict,
) -> dict:
    """Test integration connection."""
    import httpx
    
    result = {"success": False, "error": None}
    
    try:
        if integration_type == "slack":
            # Test Slack API
            token = _decrypt_credential(credentials.get("bot_token", ""))
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {token}"},
                )
                data = response.json()
                if data.get("ok"):
                    result["success"] = True
                    result["details"] = {"team": data.get("team")}
                else:
                    result["error"] = data.get("error")
        
        elif integration_type == "discord":
            # Test Discord API
            token = _decrypt_credential(credentials.get("bot_token", ""))
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://discord.com/api/v10/users/@me",
                    headers={"Authorization": f"Bot {token}"},
                )
                if response.status_code == 200:
                    data = response.json()
                    result["success"] = True
                    result["details"] = {"bot_name": data.get("username")}
                else:
                    result["error"] = f"HTTP {response.status_code}"
        
        elif integration_type in ("zapier", "make", "custom"):
            # Test webhook
            webhook_url = config.get("webhook_url")
            if webhook_url:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        webhook_url,
                        json={"test": True, "source": "taskbolt", "timestamp": datetime.utcnow().isoformat()},
                        timeout=10,
                    )
                    result["success"] = response.status_code < 400
                    result["details"] = {"response_code": response.status_code}
    
    except Exception as e:
        result["error"] = str(e)
    
    # Update integration with test result
    db = get_db()
    await db.integration.update(
        where={"id": integration_id},
        data={
            "config": {**config, "last_test_result": result},
        }
    )
    
    return result


# Import hmac for signature verification
import hmac


# Add Integration model to Prisma schema:
"""
model Integration {
  id            String   @id @default(cuid())
  tenantId      String
  type          String   // slack, discord, teams, zapier, custom
  name          String
  enabled       Boolean  @default(true)
  config        Json     @default("{}")
  credentials   Json     @default("{}") // encrypted
  lastUsedAt    DateTime?
  createdAt     DateTime @default(now())
  updatedAt     DateTime @updatedAt
  
  tenant        Tenant   @relation(fields: [tenantId], references: [id], onDelete: Cascade)
  
  @@index([tenantId])
  @@index([type])
}
"""
