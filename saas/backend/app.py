# -*- coding: utf-8 -*-
"""Taskbolt Desktop - License & AI Backend.

This is a simplified backend for the desktop app distribution model:
- License validation via Firebase Firestore
- Gumroad webhook for one-time purchase license generation
- AI LLM access for subscribed users

No frontend serving - desktop app runs locally.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import string
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Optional

import firebase_admin
from firebase_admin import credentials, firestore
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Environment configuration
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "taskbolt-490722")
GUMROAD_WEBHOOK_SECRET = os.environ.get("GUMROAD_WEBHOOK_SECRET", "")


# ============================================================================
# FIREBASE INITIALIZATION
# ============================================================================

_firestore_db = None


def get_firestore_db():
    """Get Firebase Firestore client."""
    global _firestore_db
    
    if _firestore_db is not None:
        return _firestore_db
    
    try:
        if not firebase_admin._apps:
            # Try to get credentials from env or file
            firebase_config = os.environ.get("FIREBASE_CONFIG")
            if firebase_config:
                cred_dict = json.loads(firebase_config)
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
            elif os.path.exists("/app/firebase-config.json"):
                cred = credentials.Certificate("/app/firebase-config.json")
                firebase_admin.initialize_app(cred)
            else:
                # Use default credentials (Cloud Run)
                firebase_admin.initialize_app(options={
                    "projectId": FIREBASE_PROJECT_ID,
                })
        
        _firestore_db = firestore.client()
        return _firestore_db
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        raise


# ============================================================================
# APPLICATION LIFESPAN
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    logger.info("Starting Taskbolt Desktop License Backend...")
    
    # Initialize Firebase
    try:
        get_firestore_db()
        logger.info("Firebase initialized")
    except Exception as e:
        logger.warning(f"Firebase initialization error: {e}")
    
    logger.info("Taskbolt Desktop License Backend started")
    yield
    logger.info("Taskbolt Desktop License Backend stopped")


# ============================================================================
# CREATE APPLICATION
# ============================================================================

app = FastAPI(
    title="Taskbolt Desktop",
    description="License validation and AI backend for Taskbolt Desktop",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware - allow all origins for desktop app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": "2.0.0",
        "service": "taskbolt-desktop-backend",
    }


@app.get("/api/version")
async def version():
    """Return API version."""
    return {"version": "2.0.0", "type": "desktop"}


# ============================================================================
# LICENSE MODELS
# ============================================================================

class LicenseValidateRequest(BaseModel):
    """Request model for license validation."""
    license_key: str = Field(..., min_length=16, max_length=64)
    device_id: str = Field(..., min_length=8, max_length=64)


class LicenseActivateRequest(BaseModel):
    """Request model for license activation."""
    license_key: str = Field(..., min_length=16, max_length=64)
    email: EmailStr
    device_id: str = Field(..., min_length=8, max_length=64)


class LicenseResponse(BaseModel):
    """License response model."""
    valid: bool
    status: str
    license: dict[str, Any] | None = None
    message: str | None = None


# ============================================================================
# LICENSE HELPERS
# ============================================================================

def _get_license_from_firestore(license_key: str) -> dict | None:
    """Get license data from Firestore."""
    try:
        db = get_firestore_db()
        doc_ref = db.collection("licenses").document(license_key)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
    except Exception as e:
        logger.error(f"Failed to get license from Firestore: {e}")
    return None


def _update_license_in_firestore(license_key: str, data: dict) -> bool:
    """Update license data in Firestore."""
    try:
        db = get_firestore_db()
        doc_ref = db.collection("licenses").document(license_key)
        doc_ref.update(data)
        return True
    except Exception as e:
        logger.error(f"Failed to update license in Firestore: {e}")
        return False


def _create_license_in_firestore(license_key: str, data: dict) -> bool:
    """Create a new license in Firestore."""
    try:
        db = get_firestore_db()
        doc_ref = db.collection("licenses").document(license_key)
        doc_ref.set(data)
        return True
    except Exception as e:
        logger.error(f"Failed to create license in Firestore: {e}")
        return False


def _validate_license_data(license_data: dict, device_id: str) -> tuple[bool, str]:
    """Validate license data against device ID and expiration."""
    # Check if license is active
    if license_data.get("status") != "active":
        return False, "invalid"
    
    # Check device binding
    bound_device = license_data.get("device_id")
    if bound_device and bound_device != device_id:
        return False, "device_mismatch"
    
    # Check expiration
    expires_at = license_data.get("expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if datetime.utcnow() > expires_at.replace(tzinfo=None):
            return False, "expired"
    
    return True, "valid"


# ============================================================================
# LICENSE API ENDPOINTS
# ============================================================================

@app.post("/api/license/validate", response_model=LicenseResponse)
async def validate_license(request: LicenseValidateRequest):
    """Validate a license key.
    
    This endpoint is called by the desktop app to verify license validity.
    """
    license_key = request.license_key.upper().replace("-", "").strip()
    device_id = request.device_id
    
    # Get license from Firestore
    license_data = _get_license_from_firestore(license_key)
    
    if license_data is None:
        return LicenseResponse(
            valid=False,
            status="not_found",
            message="License key not found",
        )
    
    # Validate the license
    is_valid, status = _validate_license_data(license_data, device_id)
    
    if is_valid:
        return LicenseResponse(
            valid=True,
            status="valid",
            license={
                "license_key": license_key,
                "email": license_data.get("email"),
                "plan": license_data.get("plan", "basic"),
                "device_id": license_data.get("device_id"),
                "activated_at": license_data.get("activated_at"),
                "expires_at": license_data.get("expires_at"),
                "ai_credits": license_data.get("ai_credits", 0),
                "ai_credits_used": license_data.get("ai_credits_used", 0),
                "features": license_data.get("features", []),
            },
        )
    else:
        return LicenseResponse(
            valid=False,
            status=status,
            message=f"License validation failed: {status}",
        )


@app.post("/api/license/activate", response_model=LicenseResponse)
async def activate_license(request: LicenseActivateRequest):
    """Activate a license for a specific device.
    
    This endpoint binds a license to a device for the first time.
    """
    license_key = request.license_key.upper().replace("-", "").strip()
    email = request.email
    device_id = request.device_id
    
    # Get license from Firestore
    license_data = _get_license_from_firestore(license_key)
    
    if license_data is None:
        return LicenseResponse(
            valid=False,
            status="not_found",
            message="License key not found",
        )
    
    # Check if license is already activated on another device
    bound_device = license_data.get("device_id")
    if bound_device and bound_device != device_id:
        return LicenseResponse(
            valid=False,
            status="device_mismatch",
            message="License is already activated on another device",
        )
    
    # Check if license is active/valid
    if license_data.get("status") not in ("active", "pending"):
        return LicenseResponse(
            valid=False,
            status="invalid",
            message=f"License status: {license_data.get('status')}",
        )
    
    # Activate the license
    now = datetime.utcnow()
    
    # Calculate expiration based on plan
    plan = license_data.get("plan", "basic")
    if plan == "basic":
        ai_credits = 100
        ai_validity_days = 30
    elif plan == "premium":
        ai_credits = 1000
        ai_validity_days = 30
    else:
        ai_credits = 100
        ai_validity_days = 30
    
    expires_at = now + timedelta(days=ai_validity_days)
    
    update_data = {
        "device_id": device_id,
        "email": email,
        "activated_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "ai_credits": ai_credits,
        "status": "active",
    }
    
    if _update_license_in_firestore(license_key, update_data):
        return LicenseResponse(
            valid=True,
            status="valid",
            license={
                "license_key": license_key,
                "email": email,
                "plan": plan,
                "device_id": device_id,
                "activated_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "ai_credits": ai_credits,
                "ai_credits_used": 0,
                "features": license_data.get("features", []),
            },
            message="License activated successfully",
        )
    else:
        return LicenseResponse(
            valid=False,
            status="server_error",
            message="Failed to activate license",
        )


@app.post("/api/license/create")
async def create_license(
    request: Request,
    plan: str = "basic",
    email: str | None = None,
):
    """Create a new license key (admin only).
    
    This endpoint should be protected with authentication in production.
    """
    # Generate a random license key
    chars = string.ascii_uppercase + string.digits
    license_key = "TB" + "".join(secrets.choice(chars) for _ in range(14))
    # Format: TB-XXXXX-XXXXX-XXXX
    license_key = f"{license_key[:2]}-{license_key[2:7]}-{license_key[7:12]}-{license_key[12:]}"
    
    # License data
    license_data = {
        "license_key": license_key,
        "email": email,
        "plan": plan,
        "status": "pending",
        "device_id": None,
        "activated_at": None,
        "expires_at": None,
        "ai_credits": 100 if plan == "basic" else 1000,
        "ai_credits_used": 0,
        "features": ["desktop_app", "local_models"] if plan == "basic" 
            else ["desktop_app", "local_models", "cloud_ai", "priority_support"],
        "created_at": datetime.utcnow().isoformat(),
    }
    
    if _create_license_in_firestore(license_key, license_data):
        return {
            "success": True,
            "license_key": license_key,
            "plan": plan,
            "message": "License created successfully",
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to create license",
        )


# ============================================================================
# GUMROAD WEBHOOK
# ============================================================================

@app.post("/api/webhooks/gumroad")
async def gumroad_webhook(request: Request):
    """Handle Gumroad webhook for license generation.
    
    Called when:
    - A purchase is completed
    - A subscription is created/updated/cancelled
    - A refund is issued
    """
    try:
        form_data = await request.form()
        event_type = form_data.get("event", "unknown")
        
        logger.info(f"Gumroad webhook received: {event_type}")
        
        # Verify webhook signature if configured
        if GUMROAD_WEBHOOK_SECRET:
            provided_sig = form_data.get("signature", "")
            # TODO: Implement signature verification
        
        if event_type == "purchase":
            # Extract purchase details
            email = form_data.get("email", "")
            product_id = form_data.get("product_id", "")
            product_name = form_data.get("product_name", "")
            sale_id = form_data.get("sale_id", "")
            price = float(form_data.get("price", 0)) / 100  # Convert from cents
            
            # Determine plan based on product
            plan = "basic"
            if "premium" in product_name.lower() or "pro" in product_name.lower():
                plan = "premium"
            
            # Generate license key
            chars = string.ascii_uppercase + string.digits
            license_key = "TB" + "".join(secrets.choice(chars) for _ in range(14))
            license_key = f"{license_key[:2]}-{license_key[2:7]}-{license_key[7:12]}-{license_key[12:]}"
            
            # Create license in Firestore
            license_data = {
                "license_key": license_key,
                "email": email,
                "plan": plan,
                "status": "pending",
                "device_id": None,
                "activated_at": None,
                "expires_at": None,
                "ai_credits": 100 if plan == "basic" else 1000,
                "ai_credits_used": 0,
                "features": ["desktop_app", "local_models"] if plan == "basic" 
                    else ["desktop_app", "local_models", "cloud_ai", "priority_support"],
                "created_at": datetime.utcnow().isoformat(),
                "source": "gumroad",
                "gumroad_sale_id": sale_id,
                "gumroad_product_id": product_id,
            }
            
            if _create_license_in_firestore(license_key, license_data):
                logger.info(f"License created for Gumroad purchase: {license_key} ({email})")
                
                # Send license key to customer via Gumroad
                # (Gumroad can auto-send if configured in product settings)
                
                return {
                    "success": True,
                    "message": "License created",
                    "license_key": license_key,  # Gumroad can use this in email
                }
            else:
                logger.error(f"Failed to create license for Gumroad purchase: {sale_id}")
                return {"success": False, "message": "Failed to create license"}
        
        elif event_type == "refund":
            # Handle refund - deactivate license
            sale_id = form_data.get("sale_id", "")
            # Find license by gumroad_sale_id and deactivate
            # TODO: Implement refund handling
            logger.info(f"Refund received for sale: {sale_id}")
            return {"success": True, "message": "Refund processed"}
        
        elif event_type == "subscription_updated":
            # Handle subscription update
            logger.info("Subscription updated")
            return {"success": True, "message": "Subscription updated"}
        
        elif event_type == "subscription_cancelled":
            # Handle subscription cancellation
            logger.info("Subscription cancelled")
            return {"success": True, "message": "Subscription cancelled"}
        
        else:
            logger.info(f"Unhandled Gumroad event: {event_type}")
            return {"success": True, "message": f"Event {event_type} received"}
    
    except Exception as e:
        logger.error(f"Gumroad webhook error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# STRIPE WEBHOOK (Alternative Payment)
# ============================================================================

@app.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook for license generation.
    
    Called when a checkout session is completed.
    """
    import stripe
    
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    
    try:
        if webhook_secret:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        else:
            event = json.loads(payload)
        
        event_type = event.get("type", "unknown")
        logger.info(f"Stripe webhook received: {event_type}")
        
        if event_type == "checkout.session.completed":
            session = event.get("data", {}).get("object", {})
            customer_email = session.get("customer_details", {}).get("email", "")
            metadata = session.get("metadata", {})
            plan = metadata.get("plan", "basic")
            
            # Generate license key
            chars = string.ascii_uppercase + string.digits
            license_key = "TB" + "".join(secrets.choice(chars) for _ in range(14))
            license_key = f"{license_key[:2]}-{license_key[2:7]}-{license_key[7:12]}-{license_key[12:]}"
            
            # Create license in Firestore
            license_data = {
                "license_key": license_key,
                "email": customer_email,
                "plan": plan,
                "status": "pending",
                "device_id": None,
                "activated_at": None,
                "expires_at": None,
                "ai_credits": 100 if plan == "basic" else 1000,
                "ai_credits_used": 0,
                "features": ["desktop_app", "local_models"] if plan == "basic" 
                    else ["desktop_app", "local_models", "cloud_ai", "priority_support"],
                "created_at": datetime.utcnow().isoformat(),
                "source": "stripe",
                "stripe_session_id": session.get("id"),
            }
            
            if _create_license_in_firestore(license_key, license_data):
                logger.info(f"License created for Stripe purchase: {license_key} ({customer_email})")
                return {"success": True, "license_key": license_key}
            else:
                return {"success": False, "message": "Failed to create license"}
        
        return {"success": True, "event": event_type}
    
    except Exception as e:
        logger.error(f"Stripe webhook error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
