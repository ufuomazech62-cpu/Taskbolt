# -*- coding: utf-8 -*-
"""
Taskbolt SaaS - Webhooks API

Provides webhook endpoints for external integrations:
- Generic webhook receiver
- Webhook signature verification
- Event dispatching to handlers
- Retry handling
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from prisma.models import WebhookEvent, WebhookSubscription

from ..auth import TenantContext, get_tenant_context
from ..database import get_db, TenantQuery, log_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Configuration
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
WEBHOOK_TIMEOUT = int(os.environ.get("WEBHOOK_TIMEOUT", "30"))


# ============================================================================
# MODELS
# ============================================================================

class WebhookSubscriptionCreate(BaseModel):
    """Request to create a webhook subscription."""
    name: str
    url: str
    events: List[str]  # e.g., ["chat.message", "agent.task_completed"]
    secret: Optional[str] = None
    headers: Dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class WebhookSubscriptionUpdate(BaseModel):
    """Request to update a webhook subscription."""
    name: Optional[str] = None
    url: Optional[str] = None
    events: Optional[List[str]] = None
    headers: Optional[Dict[str, str]] = None
    enabled: Optional[bool] = None


class WebhookEventPayload(BaseModel):
    """Generic webhook event payload."""
    event_type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WebhookDelivery(BaseModel):
    """Webhook delivery status."""
    id: str
    subscription_id: str
    event_type: str
    status: str  # pending, success, failed, retrying
    attempts: int
    last_attempt: Optional[datetime]
    next_retry: Optional[datetime]
    response_code: Optional[int]
    error_message: Optional[str]


# ============================================================================
# WEBHOOK SUBSCRIPTIONS API
# ============================================================================

@router.get("/subscriptions")
async def list_subscriptions(
    ctx: TenantContext = Depends(get_tenant_context)
):
    """List all webhook subscriptions for the tenant."""
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    subscriptions = await query.find_many(
        db.webhooksubscription,
        order={"createdAt": "desc"}
    )
    
    return {
        "subscriptions": [
            {
                "id": sub.id,
                "name": sub.name,
                "url": sub.url,
                "events": sub.events,
                "enabled": sub.enabled,
                "created_at": sub.createdAt.isoformat(),
            }
            for sub in subscriptions
        ]
    }


@router.post("/subscriptions")
async def create_subscription(
    request: Request,
    background_tasks: BackgroundTasks,
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Create a new webhook subscription."""
    db = get_db()
    body = await request.json()
    
    # Validate URL
    url = body.get("url", "")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    
    # Create subscription
    subscription = await db.webhooksubscription.create(
        data={
            "tenantId": ctx.tenant_id,
            "name": body.get("name", "Webhook"),
            "url": url,
            "events": body.get("events", []),
            "secret": body.get("secret", ""),
            "headers": body.get("headers", {}),
            "enabled": body.get("enabled", True),
        }
    )
    
    await log_audit(
        tenant_id=ctx.tenant_id,
        action="webhook.subscription_created",
        resource_type="webhook_subscription",
        resource_id=subscription.id,
        user_id=ctx.user_id,
        new_values={"name": subscription.name, "url": subscription.url},
    )
    
    # Send test webhook
    if body.get("send_test", False):
        background_tasks.add_task(
            send_webhook,
            subscription.id,
            "webhook.test",
            {"message": "Webhook subscription created successfully"},
        )
    
    return {
        "id": subscription.id,
        "name": subscription.name,
        "url": subscription.url,
        "events": subscription.events,
        "secret": subscription.secret[:8] + "..." if subscription.secret else None,
    }


@router.get("/subscriptions/{subscription_id}")
async def get_subscription(
    subscription_id: str,
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Get webhook subscription details."""
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    subscription = await query.find_unique(db.webhooksubscription, {"id": subscription_id})
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    # Get recent deliveries
    deliveries = await db.webhookevent.find_many(
        where={"subscriptionId": subscription_id},
        order={"createdAt": "desc"},
        take=20,
    )
    
    return {
        "id": subscription.id,
        "name": subscription.name,
        "url": subscription.url,
        "events": subscription.events,
        "headers": subscription.headers,
        "enabled": subscription.enabled,
        "created_at": subscription.createdAt.isoformat(),
        "recent_deliveries": [
            {
                "id": d.id,
                "event_type": d.eventType,
                "status": d.status,
                "attempts": d.attempts,
                "last_attempt": d.lastAttemptAt.isoformat() if d.lastAttemptAt else None,
            }
            for d in deliveries
        ],
    }


@router.patch("/subscriptions/{subscription_id}")
async def update_subscription(
    subscription_id: str,
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Update webhook subscription."""
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    subscription = await query.find_unique(db.webhooksubscription, {"id": subscription_id})
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    body = await request.json()
    update_data = {}
    
    if "name" in body:
        update_data["name"] = body["name"]
    if "url" in body:
        update_data["url"] = body["url"]
    if "events" in body:
        update_data["events"] = body["events"]
    if "headers" in body:
        update_data["headers"] = body["headers"]
    if "enabled" in body:
        update_data["enabled"] = body["enabled"]
    
    updated = await db.webhooksubscription.update(
        where={"id": subscription_id},
        data=update_data
    )
    
    return {
        "id": updated.id,
        "name": updated.name,
        "url": updated.url,
        "events": updated.events,
        "enabled": updated.enabled,
    }


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(
    subscription_id: str,
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Delete webhook subscription."""
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    subscription = await query.delete(db.webhooksubscription, {"id": subscription_id})
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    await log_audit(
        tenant_id=ctx.tenant_id,
        action="webhook.subscription_deleted",
        resource_type="webhook_subscription",
        resource_id=subscription_id,
        user_id=ctx.user_id,
    )
    
    return {"success": True}


# ============================================================================
# WEBHOOK DELIVERIES
# ============================================================================

@router.get("/deliveries")
async def list_deliveries(
    subscription_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    ctx: TenantContext = Depends(get_tenant_context)
):
    """List webhook delivery attempts."""
    db = get_db()
    query = TenantQuery(ctx.tenant_id)
    
    where = {"tenantId": ctx.tenant_id}
    if subscription_id:
        where["subscriptionId"] = subscription_id
    if status:
        where["status"] = status.upper()
    
    deliveries = await db.webhookevent.find_many(
        where=where,
        order={"createdAt": "desc"},
        take=limit,
        include={"subscription": True},
    )
    
    return {
        "deliveries": [
            {
                "id": d.id,
                "subscription_id": d.subscriptionId,
                "subscription_name": d.subscription.name if d.subscription else None,
                "event_type": d.eventType,
                "status": d.status,
                "attempts": d.attempts,
                "last_attempt": d.lastAttemptAt.isoformat() if d.lastAttemptAt else None,
                "response_code": d.responseCode,
                "error_message": d.errorMessage,
                "created_at": d.createdAt.isoformat(),
            }
            for d in deliveries
        ]
    }


@router.post("/deliveries/{delivery_id}/retry")
async def retry_delivery(
    delivery_id: str,
    background_tasks: BackgroundTasks,
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Retry a failed webhook delivery."""
    db = get_db()
    
    delivery = await db.webhookevent.find_first(
        where={
            "id": delivery_id,
            "tenantId": ctx.tenant_id,
        },
        include={"subscription": True},
    )
    
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    
    if not delivery.subscription or not delivery.subscription.enabled:
        raise HTTPException(status_code=400, detail="Subscription is not enabled")
    
    # Queue retry
    background_tasks.add_task(
        deliver_webhook,
        delivery_id,
    )
    
    return {"status": "retrying", "delivery_id": delivery_id}


# ============================================================================
# WEBHOOK SENDER
# ============================================================================

async def send_webhook(
    subscription_id: str,
    event_type: str,
    data: Dict[str, Any],
) -> None:
    """Send a webhook event to a subscription.
    
    This is called internally when events occur.
    """
    import httpx
    
    db = get_db()
    
    subscription = await db.webhooksubscription.find_unique(
        where={"id": subscription_id}
    )
    
    if not subscription or not subscription.enabled:
        logger.debug(f"Subscription {subscription_id} not found or disabled")
        return
    
    # Check if event type is subscribed
    if subscription.events and event_type not in subscription.events:
        logger.debug(f"Event {event_type} not in subscription events")
        return
    
    # Create delivery record
    delivery = await db.webhookevent.create(
        data={
            "tenantId": subscription.tenantId,
            "subscriptionId": subscription_id,
            "eventType": event_type,
            "payload": {
                "event_type": event_type,
                "timestamp": datetime.utcnow().isoformat(),
                "data": data,
            },
            "status": "PENDING",
            "attempts": 0,
        }
    )
    
    await deliver_webhook(delivery.id)


async def deliver_webhook(delivery_id: str) -> None:
    """Attempt to deliver a webhook.
    
    Handles retries and failure tracking.
    """
    import httpx
    
    db = get_db()
    
    delivery = await db.webhookevent.find_unique(
        where={"id": delivery_id},
        include={"subscription": True},
    )
    
    if not delivery or not delivery.subscription:
        return
    
    subscription = delivery.subscription
    payload = delivery.payload
    
    # Calculate signature
    payload_str = json.dumps(payload, separators=(',', ':'))
    signature = hmac.new(
        (subscription.secret or WEBHOOK_SECRET).encode(),
        payload_str.encode(),
        hashlib.sha256,
    ).hexdigest()
    
    # Prepare headers
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
        "X-Webhook-Event": delivery.eventType,
        "X-Webhook-Delivery": delivery_id,
        **(subscription.headers or {}),
    }
    
    # Update attempt count
    await db.webhookevent.update(
        where={"id": delivery_id},
        data={
            "attempts": delivery.attempts + 1,
            "lastAttemptAt": datetime.utcnow(),
        }
    )
    
    try:
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
            response = await client.post(
                subscription.url,
                content=payload_str,
                headers=headers,
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                # Success
                await db.webhookevent.update(
                    where={"id": delivery_id},
                    data={
                        "status": "SUCCESS",
                        "responseCode": response.status_code,
                    }
                )
                logger.info(f"Webhook delivered: {delivery_id}")
            else:
                raise Exception(f"HTTP {response.status_code}")
    
    except Exception as e:
        logger.warning(f"Webhook delivery failed: {delivery_id} - {e}")
        
        # Check if we should retry
        max_attempts = 5
        if delivery.attempts < max_attempts:
            # Schedule retry with exponential backoff
            retry_delays = [1, 5, 15, 60, 300]  # minutes
            retry_after = retry_delays[min(delivery.attempts, len(retry_delays) - 1)]
            
            await db.webhookevent.update(
                where={"id": delivery_id},
                data={
                    "status": "RETRYING",
                    "errorMessage": str(e),
                    "nextRetryAt": datetime.utcnow(),
                }
            )
            
            # TODO: Add to retry queue
        else:
            # Max retries exceeded
            await db.webhookevent.update(
                where={"id": delivery_id},
                data={
                    "status": "FAILED",
                    "errorMessage": str(e),
                }
            )


# ============================================================================
# EVENT EMITTER (Internal Use)
# ============================================================================

class WebhookEmitter:
    """Emit webhook events to all matching subscriptions.
    
    Usage:
        emitter = WebhookEmitter(tenant_id)
        await emitter.emit("chat.message", {"chat_id": "xxx", "message": "..."})
    """
    
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.db = get_db()
    
    async def emit(
        self,
        event_type: str,
        data: Dict[str, Any],
    ) -> List[str]:
        """Emit an event to all matching subscriptions.
        
        Returns list of delivery IDs.
        """
        # Find all matching subscriptions
        subscriptions = await self.db.webhooksubscription.find_many(
            where={
                "tenantId": self.tenant_id,
                "enabled": True,
            }
        )
        
        delivery_ids = []
        
        for sub in subscriptions:
            # Check if event matches subscription's event patterns
            if sub.events and not self._matches_events(event_type, sub.events):
                continue
            
            # Queue webhook delivery
            delivery = await self.db.webhookevent.create(
                data={
                    "tenantId": self.tenant_id,
                    "subscriptionId": sub.id,
                    "eventType": event_type,
                    "payload": {
                        "event_type": event_type,
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": data,
                    },
                    "status": "PENDING",
                    "attempts": 0,
                }
            )
            delivery_ids.append(delivery.id)
            
            # Trigger delivery (async)
            asyncio.create_task(deliver_webhook(delivery.id))
        
        return delivery_ids
    
    def _matches_events(self, event_type: str, patterns: List[str]) -> bool:
        """Check if event_type matches any pattern.
        
        Supports wildcards: "chat.*" matches "chat.message", "chat.created", etc.
        """
        for pattern in patterns:
            if pattern == "*":
                return True
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if event_type.startswith(prefix + "."):
                    return True
            elif pattern == event_type:
                return True
        return False


async def emit_webhook_event(
    tenant_id: str,
    event_type: str,
    data: Dict[str, Any],
) -> List[str]:
    """Convenience function to emit webhook events."""
    emitter = WebhookEmitter(tenant_id)
    return await emitter.emit(event_type, data)


# Add WebhookSubscription and WebhookEvent to Prisma schema if needed
# These models should be added to the Prisma schema:

"""
model WebhookSubscription {
  id          String   @id @default(cuid())
  tenantId    String
  name        String
  url         String
  events      Json     @default("[]")
  secret      String?
  headers     Json     @default("{}")
  enabled     Boolean  @default(true)
  createdAt   DateTime @default(now())
  updatedAt   DateTime @updatedAt
  
  tenant      Tenant   @relation(fields: [tenantId], references: [id], onDelete: Cascade)
  deliveries  WebhookEvent[]
  
  @@index([tenantId])
}

model WebhookEvent {
  id              String   @id @default(cuid())
  tenantId        String
  subscriptionId  String
  eventType       String
  payload         Json
  status          String   @default("PENDING") // PENDING, SUCCESS, FAILED, RETRYING
  attempts        Int      @default(0)
  lastAttemptAt   DateTime?
  nextRetryAt     DateTime?
  responseCode    Int?
  errorMessage    String?  @db.Text
  createdAt       DateTime @default(now())
  
  tenant          Tenant              @relation(fields: [tenantId], references: [id], onDelete: Cascade)
  subscription    WebhookSubscription @relation(fields: [subscriptionId], references: [id], onDelete: Cascade)
  
  @@index([tenantId])
  @@index([subscriptionId])
  @@index([status])
}
"""
