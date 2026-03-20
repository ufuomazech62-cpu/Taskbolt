# -*- coding: utf-8 -*-
"""License Manager for Taskbolt Desktop.

Handles license validation, storage, and communication with Firebase.
Supports both online validation and offline grace periods.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from .hardware_id import get_hardware_id

logger = logging.getLogger(__name__)

# License cache file location
LICENSE_CACHE_FILENAME = "license_cache.json"


class LicenseStatus(Enum):
    """License validation status."""
    VALID = "valid"
    EXPIRED = "expired"
    INVALID = "invalid"
    NOT_FOUND = "not_found"
    DEVICE_MISMATCH = "device_mismatch"
    OFFLINE_GRACE = "offline_grace"
    SERVER_ERROR = "server_error"


@dataclass
class LicenseInfo:
    """License information."""
    license_key: str
    email: str | None = None
    plan: str = "basic"
    device_id: str | None = None
    activated_at: datetime | None = None
    expires_at: datetime | None = None
    ai_credits: int = 0
    ai_credits_used: int = 0
    features: list[str] | None = None
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LicenseInfo:
        """Create LicenseInfo from dictionary."""
        return cls(
            license_key=data.get("license_key", ""),
            email=data.get("email"),
            plan=data.get("plan", "basic"),
            device_id=data.get("device_id"),
            activated_at=_parse_datetime(data.get("activated_at")),
            expires_at=_parse_datetime(data.get("expires_at")),
            ai_credits=data.get("ai_credits", 0),
            ai_credits_used=data.get("ai_credits_used", 0),
            features=data.get("features"),
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for caching."""
        return {
            "license_key": self.license_key,
            "email": self.email,
            "plan": self.plan,
            "device_id": self.device_id,
            "activated_at": _format_datetime(self.activated_at),
            "expires_at": _format_datetime(self.expires_at),
            "ai_credits": self.ai_credits,
            "ai_credits_used": self.ai_credits_used,
            "features": self.features,
        }


def _parse_datetime(value: Any) -> datetime | None:
    """Parse datetime from various formats."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Try ISO format first
        for fmt in [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def _format_datetime(value: datetime | None) -> str | None:
    """Format datetime for JSON serialization."""
    if value is None:
        return None
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


class LicenseManager:
    """Manages license validation and caching for Taskbolt Desktop.
    
    Features:
    - Online license validation via Firebase
    - Offline grace period (7 days)
    - Device binding
    - Local cache for offline use
    """
    
    # Offline grace period in days
    OFFLINE_GRACE_DAYS = 7
    
    def __init__(
        self,
        firebase_project_id: str | None = None,
        api_key: str | None = None,
        cache_dir: Path | None = None,
    ):
        """Initialize the license manager.
        
        Args:
            firebase_project_id: Firebase project ID for license server
            api_key: Firebase API key
            cache_dir: Directory for license cache
        """
        self.firebase_project_id = firebase_project_id or os.environ.get(
            "TASKBOLT_FIREBASE_PROJECT_ID",
            "taskbolt-490722",
        )
        self.api_key = api_key or os.environ.get("TASKBOLT_FIREBASE_API_KEY")
        
        # Cache directory
        if cache_dir is None:
            cache_dir = Path.home() / ".taskbolt"
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self._cache_file = self.cache_dir / LICENSE_CACHE_FILENAME
        self._cached_license: LicenseInfo | None = None
        self._last_validation: datetime | None = None
    
    @property
    def hardware_id(self) -> str:
        """Get the hardware ID for this device."""
        return get_hardware_id()
    
    def _load_cache(self) -> dict | None:
        """Load cached license data."""
        if self._cache_file.exists():
            try:
                return json.loads(self._cache_file.read_text())
            except Exception as e:
                logger.warning(f"Failed to load license cache: {e}")
        return None
    
    def _save_cache(self, data: dict) -> None:
        """Save license data to cache."""
        try:
            self._cache_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save license cache: {e}")
    
    def _update_last_validation(self) -> None:
        """Update last validation timestamp in cache."""
        cache = self._load_cache() or {}
        cache["last_validation"] = time.time()
        self._save_cache(cache)
        self._last_validation = datetime.now()
    
    def _is_offline_grace_valid(self) -> bool:
        """Check if we're within offline grace period."""
        cache = self._load_cache()
        if not cache or "last_validation" not in cache:
            return False
        
        last_validation = datetime.fromtimestamp(cache["last_validation"])
        grace_expiry = last_validation + timedelta(days=self.OFFLINE_GRACE_DAYS)
        
        return datetime.now() < grace_expiry
    
    def _get_cached_license(self) -> LicenseInfo | None:
        """Get cached license info."""
        cache = self._load_cache()
        if cache and "license" in cache:
            return LicenseInfo.from_dict(cache["license"])
        return None
    
    def validate_online(
        self,
        license_key: str,
        id_token: str | None = None,
    ) -> tuple[LicenseStatus, LicenseInfo | None]:
        """Validate license online via Firebase.
        
        Args:
            license_key: The license key to validate
            id_token: Firebase ID token for authenticated requests
            
        Returns:
            Tuple of (status, license_info)
        """
        import urllib.request
        import urllib.error
        
        # Use Cloud Run backend for license validation
        # This endpoint will be created in the backend
        api_url = os.environ.get(
            "TASKBOLT_API_URL",
            f"https://taskbolt-rwprduf6iq-uc.a.run.app",
        )
        
        url = f"{api_url}/api/license/validate"
        
        payload = {
            "license_key": license_key,
            "device_id": self.hardware_id,
        }
        
        headers = {
            "Content-Type": "application/json",
        }
        if id_token:
            headers["Authorization"] = f"Bearer {id_token}"
        
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers=headers,
                method="POST",
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                
                if data.get("valid"):
                    license_info = LicenseInfo.from_dict(data.get("license", {}))
                    license_info.license_key = license_key
                    
                    # Cache the valid license
                    self._save_cache({
                        "license": license_info.to_dict(),
                        "last_validation": time.time(),
                    })
                    self._cached_license = license_info
                    
                    return LicenseStatus.VALID, license_info
                else:
                    status_str = data.get("status", "invalid")
                    try:
                        status = LicenseStatus(status_str)
                    except ValueError:
                        status = LicenseStatus.INVALID
                    return status, None
                    
        except urllib.error.HTTPError as e:
            logger.error(f"License validation HTTP error: {e.code}")
            return LicenseStatus.SERVER_ERROR, None
        except urllib.error.URLError as e:
            logger.warning(f"License validation network error: {e}")
            # Network error - check offline grace
            if self._is_offline_grace_valid():
                cached = self._get_cached_license()
                if cached:
                    return LicenseStatus.OFFLINE_GRACE, cached
            return LicenseStatus.SERVER_ERROR, None
        except Exception as e:
            logger.error(f"License validation error: {e}")
            return LicenseStatus.SERVER_ERROR, None
    
    def validate(self, license_key: str | None = None) -> tuple[LicenseStatus, LicenseInfo | None]:
        """Validate license, with offline grace fallback.
        
        Args:
            license_key: License key to validate. If None, uses cached license.
            
        Returns:
            Tuple of (status, license_info)
        """
        # Try to get license key from cache if not provided
        if license_key is None:
            cached = self._get_cached_license()
            if cached:
                license_key = cached.license_key
            else:
                return LicenseStatus.NOT_FOUND, None
        
        # Try online validation
        status, info = self.validate_online(license_key)
        
        if status == LicenseStatus.VALID:
            return status, info
        
        # Online failed, check offline grace
        if status in (
            LicenseStatus.SERVER_ERROR,
            LicenseStatus.OFFLINE_GRACE,
        ):
            if self._is_offline_grace_valid():
                cached = self._get_cached_license()
                if cached and cached.license_key == license_key:
                    logger.info("Using offline grace period for license validation")
                    return LicenseStatus.OFFLINE_GRACE, cached
        
        return status, info
    
    def activate(
        self,
        license_key: str,
        email: str,
        id_token: str | None = None,
    ) -> tuple[LicenseStatus, LicenseInfo | None]:
        """Activate a license for this device.
        
        Args:
            license_key: The license key to activate
            email: User email
            id_token: Firebase ID token for authentication
            
        Returns:
            Tuple of (status, license_info)
        """
        import urllib.request
        import urllib.error
        
        api_url = os.environ.get(
            "TASKBOLT_API_URL",
            f"https://taskbolt-rwprduf6iq-uc.a.run.app",
        )
        
        url = f"{api_url}/api/license/activate"
        
        payload = {
            "license_key": license_key,
            "email": email,
            "device_id": self.hardware_id,
        }
        
        headers = {
            "Content-Type": "application/json",
        }
        if id_token:
            headers["Authorization"] = f"Bearer {id_token}"
        
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers=headers,
                method="POST",
            )
            
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode())
                
                if data.get("success"):
                    license_info = LicenseInfo.from_dict(data.get("license", {}))
                    license_info.license_key = license_key
                    
                    # Cache the activated license
                    self._save_cache({
                        "license": license_info.to_dict(),
                        "last_validation": time.time(),
                    })
                    self._cached_license = license_info
                    
                    return LicenseStatus.VALID, license_info
                else:
                    status_str = data.get("status", "invalid")
                    try:
                        status = LicenseStatus(status_str)
                    except ValueError:
                        status = LicenseStatus.INVALID
                    return status, None
                    
        except urllib.error.HTTPError as e:
            logger.error(f"License activation HTTP error: {e.code}")
            try:
                error_body = json.loads(e.read().decode())
                logger.error(f"Error response: {error_body}")
            except Exception:
                pass
            return LicenseStatus.SERVER_ERROR, None
        except urllib.error.URLError as e:
            logger.error(f"License activation network error: {e}")
            return LicenseStatus.SERVER_ERROR, None
        except Exception as e:
            logger.error(f"License activation error: {e}")
            return LicenseStatus.SERVER_ERROR, None
    
    def get_license(self) -> LicenseInfo | None:
        """Get current cached license info."""
        return self._get_cached_license()
    
    def clear_license(self) -> None:
        """Clear cached license."""
        if self._cache_file.exists():
            self._cache_file.unlink()
        self._cached_license = None
        self._last_validation = None
    
    def get_ai_credits_remaining(self) -> int:
        """Get remaining AI credits for subscription users."""
        license_info = self.get_license()
        if license_info:
            return max(0, license_info.ai_credits - license_info.ai_credits_used)
        return 0
    
    def is_premium(self) -> bool:
        """Check if user has premium features."""
        license_info = self.get_license()
        if license_info:
            return license_info.plan in ("premium", "pro", "enterprise")
        return False


# Global license manager instance
_license_manager: LicenseManager | None = None


def get_license_manager() -> LicenseManager:
    """Get the global license manager instance."""
    global _license_manager
    if _license_manager is None:
        _license_manager = LicenseManager()
    return _license_manager
