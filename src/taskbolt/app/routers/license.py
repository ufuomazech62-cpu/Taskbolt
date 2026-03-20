# -*- coding: utf-8 -*-
"""License API endpoints for Taskbolt Desktop.

Provides license validation, activation, and management endpoints.
Uses Firebase Firestore for license storage.
"""

from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/license", tags=["license"])


# --- Request/Response Models ---

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


class LicenseInfo(BaseModel):
    """License information model."""
    license_key: str
    email: str | None = None
    plan: str = "basic"
    device_id: str | None = None
    activated_at: datetime | None = None
    expires_at: datetime | None = None
    ai_credits: int = 0
    ai_credits_used: int = 0
    features: list[str] = []


# --- Firebase Integration ---

def _get_firestore_client():
    """Get Firebase Firestore client."""
    try:
        import firebase_admin
        from firebase_admin import firestore
        
        if not firebase_admin._apps:
            # Initialize Firebase Admin SDK
            import os
            from firebase_admin import credentials
            
            # Try to get credentials from env or file
            cred = None
            firebase_config = os.environ.get("FIREBASE_CONFIG")
            if firebase_config:
                import json
                cred_dict = json.loads(firebase_config)
                cred = credentials.Certificate(cred_dict)
            elif os.path.exists("/app/firebase-config.json"):
                cred = credentials.Certificate("/app/firebase-config.json")
            
            if cred:
                firebase_admin.initialize_app(cred)
            else:
                raise RuntimeError("Firebase credentials not configured")
        
        return firestore.client()
    except ImportError:
        logger.warning("Firebase Admin SDK not installed")
        return None


def _get_license_from_firestore(license_key: str) -> dict | None:
    """Get license data from Firestore."""
    db = _get_firestore_client()
    if db is None:
        return None
    
    try:
        doc_ref = db.collection("licenses").document(license_key)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
    except Exception as e:
        logger.error(f"Failed to get license from Firestore: {e}")
    return None


def _update_license_in_firestore(license_key: str, data: dict) -> bool:
    """Update license data in Firestore."""
    db = _get_firestore_client()
    if db is None:
        return False
    
    try:
        doc_ref = db.collection("licenses").document(license_key)
        doc_ref.update(data)
        return True
    except Exception as e:
        logger.error(f"Failed to update license in Firestore: {e}")
        return False


def _create_license_in_firestore(license_key: str, data: dict) -> bool:
    """Create a new license in Firestore."""
    db = _get_firestore_client()
    if db is None:
        return False
    
    try:
        doc_ref = db.collection("licenses").document(license_key)
        doc_ref.set(data)
        return True
    except Exception as e:
        logger.error(f"Failed to create license in Firestore: {e}")
        return False


# --- License Validation Logic ---

def _validate_license_data(license_data: dict, device_id: str) -> tuple[bool, str]:
    """Validate license data against device ID and expiration.
    
    Returns:
        Tuple of (is_valid, status)
    """
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
            from datetime import datetime
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if datetime.utcnow() > expires_at.replace(tzinfo=None):
            return False, "expired"
    
    return True, "valid"


# --- API Endpoints ---

@router.post("/validate", response_model=LicenseResponse)
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
        # Return license info (sanitized)
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


@router.post("/activate", response_model=LicenseResponse)
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
    
    # Calculate expiration (e.g., 1 month from activation for one-time purchase)
    plan = license_data.get("plan", "basic")
    if plan == "basic":
        ai_credits = 100  # 100 AI credits for basic plan
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
        # Return the updated license
        updated_license = {**license_data, **update_data}
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


@router.post("/deactivate")
async def deactivate_license(request: Request):
    """Deactivate a license (remove device binding)."""
    # TODO: Implement license deactivation
    # This would typically require authentication
    return {"success": False, "message": "Not implemented"}


@router.post("/create")
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
        "status": "pending",  # Pending activation
        "device_id": None,
        "activated_at": None,
        "expires_at": None,
        "ai_credits": 100 if plan == "basic" else 1000,
        "ai_credits_used": 0,
        "features": ["desktop_app", "local_models"] if plan == "basic" else ["desktop_app", "local_models", "cloud_ai", "priority_support"],
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


@router.get("/check")
async def check_license_status(request: Request):
    """Check if a license is valid for the current device.
    
    This is a convenience endpoint that combines validate with device ID lookup.
    """
    return {
        "status": "ok",
        "message": "License check endpoint",
    }


# --- Gumroad Webhook ---

@router.post("/webhook/gumroad")
async def gumroad_webhook(request: Request):
    """Handle Gumroad webhook for license generation.
    
    Called when:
    - A purchase is completed
    - A subscription is created/updated/cancelled
    - A refund is issued
    """
    import os
    
    try:
        form_data = await request.form()
        event_type = form_data.get("event", "unknown")
        
        logger.info(f"Gumroad webhook received: {event_type}")
        
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
                return {
                    "success": True,
                    "message": "License created",
                    "license_key": license_key,
                }
            else:
                logger.error(f"Failed to create license for Gumroad purchase: {sale_id}")
                return {"success": False, "message": "Failed to create license"}
        
        elif event_type == "refund":
            sale_id = form_data.get("sale_id", "")
            logger.info(f"Refund received for sale: {sale_id}")
            return {"success": True, "message": "Refund processed"}
        
        elif event_type == "subscription_updated":
            logger.info("Subscription updated")
            return {"success": True, "message": "Subscription updated"}
        
        elif event_type == "subscription_cancelled":
            logger.info("Subscription cancelled")
            return {"success": True, "message": "Subscription cancelled"}
        
        else:
            logger.info(f"Unhandled Gumroad event: {event_type}")
            return {"success": True, "message": f"Event {event_type} received"}
    
    except Exception as e:
        logger.error(f"Gumroad webhook error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
