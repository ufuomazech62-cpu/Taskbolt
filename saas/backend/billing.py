# -*- coding: utf-8 -*-
"""Stripe Billing Integration for Taskbolt SaaS.

Handles:
- Subscription management
- Payment processing
- Plan upgrades/downgrades
- Webhook handling
- Usage-based billing
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List

import stripe
from fastapi import Request, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Configuration
STRIPE_API_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")

# Initialize Stripe
if STRIPE_API_KEY:
    stripe.api_key = STRIPE_API_KEY


# ============================================================================
# PRICING PLANS
# ============================================================================

@dataclass
class PricingPlan:
    """Pricing plan configuration."""
    id: str
    name: str
    stripe_price_id: str
    price_cents: int
    limits: Dict[str, int]
    features: List[str]


PLANS = {
    "FREE": PricingPlan(
        id="free",
        name="Free",
        stripe_price_id="",  # No Stripe price for free tier
        price_cents=0,
        limits={
            "max_agents": 1,
            "max_users": 1,
            "max_storage_bytes": 1_073_741_824,  # 1GB
            "rate_limit_per_minute": 30,
        },
        features=[
            "1 Agent",
            "1 User",
            "1GB Storage",
            "Basic Support",
        ],
    ),
    "STARTER": PricingPlan(
        id="starter",
        name="Starter",
        stripe_price_id=os.environ.get("STRIPE_PRICE_STARTER", "price_starter"),
        price_cents=1900,  # $19/month
        limits={
            "max_agents": 3,
            "max_users": 5,
            "max_storage_bytes": 10_737_418_240,  # 10GB
            "rate_limit_per_minute": 60,
        },
        features=[
            "3 Agents",
            "5 Users",
            "10GB Storage",
            "Email Support",
            "API Access",
        ],
    ),
    "PROFESSIONAL": PricingPlan(
        id="professional",
        name="Professional",
        stripe_price_id=os.environ.get("STRIPE_PRICE_PROFESSIONAL", "price_professional"),
        price_cents=4900,  # $49/month
        limits={
            "max_agents": 10,
            "max_users": 25,
            "max_storage_bytes": 107_374_182_400,  # 100GB
            "rate_limit_per_minute": 120,
        },
        features=[
            "10 Agents",
            "25 Users",
            "100GB Storage",
            "Priority Support",
            "API Access",
            "Custom Integrations",
            "Audit Logs",
        ],
    ),
    "ENTERPRISE": PricingPlan(
        id="enterprise",
        name="Enterprise",
        stripe_price_id=os.environ.get("STRIPE_PRICE_ENTERPRISE", "price_enterprise"),
        price_cents=19900,  # $199/month
        limits={
            "max_agents": 100,
            "max_users": 1000,
            "max_storage_bytes": 1_099_511_627_776,  # 1TB
            "rate_limit_per_minute": 300,
        },
        features=[
            "Unlimited Agents",
            "Unlimited Users",
            "1TB Storage",
            "24/7 Support",
            "API Access",
            "Custom Integrations",
            "Audit Logs",
            "SSO/SAML",
            "Dedicated Infrastructure",
            "SLA",
        ],
    ),
}


# ============================================================================
# MODELS
# ============================================================================

class CreateCheckoutSession(BaseModel):
    """Request to create a checkout session."""
    price_id: str
    success_url: str
    cancel_url: str


class SubscriptionUpdate(BaseModel):
    """Request to update subscription."""
    plan: str


# ============================================================================
# BILLING SERVICE
# ============================================================================

class BillingService:
    """Stripe billing integration service."""
    
    def __init__(self):
        self.stripe = stripe
    
    async def create_customer(
        self,
        email: str,
        name: str,
        tenant_id: str,
    ) -> str:
        """Create a Stripe customer for a tenant.
        
        Args:
            email: Customer email
            name: Customer/Company name
            tenant_id: Internal tenant ID
            
        Returns:
            Stripe customer ID
        """
        customer = self.stripe.Customer.create(
            email=email,
            name=name,
            metadata={
                "tenant_id": tenant_id,
            }
        )
        logger.info(f"Created Stripe customer: {customer.id} for tenant: {tenant_id}")
        return customer.id
    
    async def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """Create a Stripe checkout session.
        
        Args:
            customer_id: Stripe customer ID
            price_id: Stripe price ID
            success_url: URL to redirect on success
            cancel_url: URL to redirect on cancel
            
        Returns:
            Checkout session URL
        """
        session = self.stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{
                "price": price_id,
                "quantity": 1,
            }],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            allow_promotion_codes=True,
        )
        return session.url
    
    async def create_portal_session(
        self,
        customer_id: str,
        return_url: str,
    ) -> str:
        """Create a customer portal session for self-service.
        
        Args:
            customer_id: Stripe customer ID
            return_url: URL to return after portal session
            
        Returns:
            Portal session URL
        """
        session = self.stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return session.url
    
    async def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Get subscription details."""
        subscription = self.stripe.Subscription.retrieve(subscription_id)
        return {
            "id": subscription.id,
            "status": subscription.status,
            "current_period_start": datetime.fromtimestamp(subscription.current_period_start),
            "current_period_end": datetime.fromtimestamp(subscription.current_period_end),
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "plan_id": subscription.plan.id if subscription.plan else None,
        }
    
    async def cancel_subscription(
        self,
        subscription_id: str,
        immediately: bool = False,
    ) -> Dict[str, Any]:
        """Cancel a subscription.
        
        Args:
            subscription_id: Stripe subscription ID
            immediately: Cancel immediately or at period end
            
        Returns:
            Updated subscription details
        """
        if immediately:
            subscription = self.stripe.Subscription.delete(subscription_id)
        else:
            subscription = self.stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True
            )
        
        logger.info(f"Cancelled subscription: {subscription_id}")
        return await self.get_subscription(subscription_id)
    
    async def update_subscription_plan(
        self,
        subscription_id: str,
        new_price_id: str,
    ) -> Dict[str, Any]:
        """Update subscription to a new plan.
        
        Args:
            subscription_id: Stripe subscription ID
            new_price_id: New Stripe price ID
            
        Returns:
            Updated subscription details
        """
        subscription = self.stripe.Subscription.retrieve(subscription_id)
        
        # Update with proration
        updated = self.stripe.Subscription.modify(
            subscription_id,
            items=[{
                "id": subscription["items"]["data"][0].id,
                "price": new_price_id,
            }],
            payment_behavior="pending_if_incomplete",
            proration_behavior="create_prorations",
        )
        
        logger.info(f"Updated subscription {subscription_id} to price {new_price_id}")
        return await self.get_subscription(subscription_id)
    
    async def report_usage(
        self,
        subscription_item_id: str,
        quantity: int,
        timestamp: Optional[int] = None,
    ) -> str:
        """Report usage for metered billing.
        
        Args:
            subscription_item_id: Stripe subscription item ID
            quantity: Usage quantity (e.g., tokens)
            timestamp: Unix timestamp (defaults to now)
            
        Returns:
            Usage record ID
        """
        if timestamp is None:
            timestamp = int(datetime.utcnow().timestamp())
        
        record = self.stripe.SubscriptionItem.create_usage_record(
            subscription_item_id,
            quantity=quantity,
            timestamp=timestamp,
            action="increment",
        )
        
        return record.id


# Global billing service
_billing_service: Optional[BillingService] = None


def get_billing_service() -> BillingService:
    """Get the billing service instance."""
    global _billing_service
    if _billing_service is None:
        if not STRIPE_API_KEY:
            raise RuntimeError("Stripe API key not configured")
        _billing_service = BillingService()
    return _billing_service


# ============================================================================
# WEBHOOK HANDLER
# ============================================================================

class StripeWebhookHandler:
    """Handle Stripe webhooks."""
    
    def __init__(self):
        self.billing = get_billing_service()
    
    async def handle_webhook(
        self,
        payload: bytes,
        sig_header: str,
    ) -> Dict[str, str]:
        """Handle incoming Stripe webhook.
        
        Args:
            payload: Raw request body
            sig_header: Stripe-Signature header
            
        Returns:
            Result status
        """
        try:
            event = self.billing.stripe.Webhook.construct_event(
                payload,
                sig_header,
                STRIPE_WEBHOOK_SECRET,
            )
        except self.billing.stripe.SignatureVerificationError as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        # Handle event types
        event_type = event["type"]
        data = event["data"]["object"]
        
        handlers = {
            "checkout.session.completed": self._handle_checkout_complete,
            "customer.subscription.created": self._handle_subscription_created,
            "customer.subscription.updated": self._handle_subscription_updated,
            "customer.subscription.deleted": self._handle_subscription_deleted,
            "invoice.payment_succeeded": self._handle_payment_succeeded,
            "invoice.payment_failed": self._handle_payment_failed,
        }
        
        handler = handlers.get(event_type)
        if handler:
            await handler(data)
        else:
            logger.info(f"Unhandled webhook event type: {event_type}")
        
        return {"status": "processed", "event_type": event_type}
    
    async def _handle_checkout_complete(self, session: Dict[str, Any]):
        """Handle completed checkout session."""
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        
        logger.info(f"Checkout completed: customer={customer_id}, subscription={subscription_id}")
        
        # Update tenant in database
        # This should update the tenant's stripe_subscription_id and plan
        # based on the price they purchased
    
    async def _handle_subscription_created(self, subscription: Dict[str, Any]):
        """Handle subscription created."""
        customer_id = subscription.get("customer")
        subscription_id = subscription.get("id")
        
        logger.info(f"Subscription created: {subscription_id} for customer: {customer_id}")
    
    async def _handle_subscription_updated(self, subscription: Dict[str, Any]):
        """Handle subscription updated (plan change)."""
        customer_id = subscription.get("customer")
        subscription_id = subscription.get("id")
        status = subscription.get("status")
        
        logger.info(f"Subscription updated: {subscription_id}, status: {status}")
        
        # Update tenant plan based on the new price
        # This should query the database by stripe_customer_id and update the plan
    
    async def _handle_subscription_deleted(self, subscription: Dict[str, Any]):
        """Handle subscription cancelled/deleted."""
        customer_id = subscription.get("customer")
        
        logger.info(f"Subscription deleted for customer: {customer_id}")
        
        # Downgrade tenant to free tier
        # This should update the tenant's plan to FREE
    
    async def _handle_payment_succeeded(self, invoice: Dict[str, Any]):
        """Handle successful payment."""
        customer_id = invoice.get("customer")
        amount = invoice.get("amount_paid", 0)
        
        logger.info(f"Payment succeeded: ${amount/100:.2f} from customer: {customer_id}")
    
    async def _handle_payment_failed(self, invoice: Dict[str, Any]):
        """Handle failed payment."""
        customer_id = invoice.get("customer")
        
        logger.warning(f"Payment failed for customer: {customer_id}")
        
        # Could send email notification, update tenant status, etc.


# ============================================================================
# API ROUTES (to be added to app.py)
# ============================================================================

# These routes should be added to the FastAPI app
"""
@app.get("/api/billing/plans")
async def list_plans():
    return {
        "plans": [
            {
                "id": plan.id,
                "name": plan.name,
                "price": plan.price_cents / 100,
                "limits": plan.limits,
                "features": plan.features,
            }
            for plan in PLANS.values()
        ]
    }

@app.post("/api/billing/checkout")
async def create_checkout(
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context)
):
    billing = get_billing_service()
    
    body = await request.json()
    price_id = body.get("price_id")
    
    # Get tenant's Stripe customer ID or create one
    # ...
    
    session_url = await billing.create_checkout_session(
        customer_id=stripe_customer_id,
        price_id=price_id,
        success_url=body.get("success_url"),
        cancel_url=body.get("cancel_url"),
    )
    
    return {"checkout_url": session_url}

@app.post("/api/billing/portal")
async def create_portal(
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context)
):
    billing = get_billing_service()
    
    portal_url = await billing.create_portal_session(
        customer_id=stripe_customer_id,
        return_url=body.get("return_url"),
    )
    
    return {"portal_url": portal_url}

@app.post("/api/billing/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    handler = StripeWebhookHandler()
    return await handler.handle_webhook(payload, sig_header)
"""
