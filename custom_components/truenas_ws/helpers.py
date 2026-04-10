"""Helper utilities for the TrueNAS integration."""

from __future__ import annotations


def format_bytes(size_bytes: int | float) -> str:
    """Format bytes into a human-readable string."""
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} EiB"


def bytes_to_gib(size_bytes: int | float) -> float:
    """Convert bytes to GiB, rounded to 2 decimals."""
    return round(size_bytes / (1024**3), 2)


def safe_get(data: dict, *keys: str, default: object = None) -> object:
    """Safely traverse nested dict keys."""
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current
