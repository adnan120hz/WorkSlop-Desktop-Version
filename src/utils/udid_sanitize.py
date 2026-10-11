"""Allowlist sanitizer for device UDIDs used in local paths.

The UDID is device-reported over USB, so it must never become a raw path
segment: a hostile device could hand us ``..`` and walk the backup pool.
This module is deliberately stdlib-only so leaf modules (e.g.
``src/restore/inject.py``) can import it without creating import cycles.
"""
import re

_UDID_BAD = re.compile(r"[^A-Za-z0-9-]")


def sanitize_udid(udid: str) -> str:
    """Allowlist-sanitize a device UDID for safe use in local paths."""
    s = _UDID_BAD.sub("_", str(udid or "")).strip("_")
    return (s or "unknown-device")[:64]
