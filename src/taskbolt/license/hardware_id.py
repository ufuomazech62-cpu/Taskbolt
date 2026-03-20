# -*- coding: utf-8 -*-
"""Hardware ID generation for license binding.

Generates a unique identifier for the machine to bind licenses to specific devices.
"""

import hashlib
import platform
import subprocess
import sys
from pathlib import Path


def _run_command(cmd: list[str]) -> str:
    """Run a command and return its output, or empty string on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _get_windows_hardware_info() -> dict[str, str]:
    """Get Windows hardware identifiers using WMI."""
    info = {}
    
    # Get motherboard serial
    result = _run_command([
        "wmic", "baseboard", "get", "serialnumber"
    ])
    if result:
        lines = [l.strip() for l in result.split("\n") if l.strip()]
        if len(lines) > 1:
            info["motherboard"] = lines[1]
    
    # Get CPU ID
    result = _run_command([
        "wmic", "cpu", "get", "processorid"
    ])
    if result:
        lines = [l.strip() for l in result.split("\n") if l.strip()]
        if len(lines) > 1:
            info["cpu"] = lines[1]
    
    # Get BIOS serial
    result = _run_command([
        "wmic", "bios", "get", "serialnumber"
    ])
    if result:
        lines = [l.strip() for l in result.split("\n") if l.strip()]
        if len(lines) > 1:
            info["bios"] = lines[1]
    
    return info


def _get_macos_hardware_info() -> dict[str, str]:
    """Get macOS hardware identifiers using system_profiler and ioreg."""
    info = {}
    
    # Get hardware UUID
    result = _run_command([
        "ioreg", "-rd1", "-c", "IOPlatformExpertDevice"
    ])
    if "IOPlatformUUID" in result:
        for line in result.split("\n"):
            if "IOPlatformUUID" in line:
                # Extract UUID from line like: "IOPlatformUUID" = "xxx-xxx-xxx"
                parts = line.split("=")
                if len(parts) > 1:
                    info["platform_uuid"] = parts[1].strip().strip('"')
    
    # Get serial number
    result = _run_command([
        "system_profiler", "SPHardwareDataType"
    ])
    if "Serial Number" in result:
        for line in result.split("\n"):
            if "Serial Number" in line:
                parts = line.split(":")
                if len(parts) > 1:
                    info["serial"] = parts[1].strip()
    
    return info


def _get_linux_hardware_info() -> dict[str, str]:
    """Get Linux hardware identifiers."""
    info = {}
    
    # Get machine-id (unique per installation)
    machine_id_paths = [
        "/etc/machine-id",
        "/var/lib/dbus/machine-id",
    ]
    for path in machine_id_paths:
        p = Path(path)
        if p.exists():
            info["machine_id"] = p.read_text().strip()
            break
    
    # Get CPU info
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        content = cpuinfo.read_text()
        for line in content.split("\n"):
            if line.startswith("model name"):
                info["cpu_model"] = line.split(":")[1].strip()
                break
    
    return info


def get_hardware_id() -> str:
    """Generate a unique hardware ID for this machine.
    
    Returns a SHA-256 hash of hardware-specific identifiers.
    This ID is used to bind licenses to specific devices.
    """
    system = platform.system().lower()
    
    if system == "windows":
        info = _get_windows_hardware_info()
    elif system == "darwin":
        info = _get_macos_hardware_info()
    elif system == "linux":
        info = _get_linux_hardware_info()
    else:
        # Fallback to basic platform info
        info = {
            "system": platform.system(),
            "node": platform.node(),
            "machine": platform.machine(),
        }
    
    # Add common identifiers
    info["os"] = system
    info["machine"] = platform.machine()
    info["node"] = platform.node()
    
    # Create a sorted, deterministic string from the info
    sorted_items = sorted(info.items())
    hardware_string = "|".join(f"{k}={v}" for k, v in sorted_items if v)
    
    # Hash to get a fixed-length ID
    hardware_id = hashlib.sha256(hardware_string.encode()).hexdigest()[:32]
    
    return hardware_id


if __name__ == "__main__":
    print(f"Hardware ID: {get_hardware_id()}")
    print(f"System: {platform.system()}")
    print(f"Machine: {platform.machine()}")
