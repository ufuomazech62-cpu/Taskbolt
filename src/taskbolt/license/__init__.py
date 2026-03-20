# -*- coding: utf-8 -*-
"""Taskbolt License Management System.

This module provides license validation for the desktop application.
Licenses are stored in Firebase Firestore and validated on app startup.
"""

from .license_manager import LicenseManager, LicenseStatus
from .hardware_id import get_hardware_id

__all__ = ["LicenseManager", "LicenseStatus", "get_hardware_id"]
