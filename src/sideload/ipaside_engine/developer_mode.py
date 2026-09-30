"""iOS Developer Mode (iOS 16+).

Development-signed apps only run when Developer Mode is enabled, which is
required for sideloading on iOS 16 and later. This module reports the current
status and can trigger the enable flow (which reboots the device and then
requires the user to confirm in Settings).
"""

from __future__ import annotations

from typing import Any

from . import lockdown
from ._asyncutil import maybe_await, run

_AMFI_DOMAIN = "com.apple.security.mac.amfi"


def _major_version(product_version: str | None) -> int | None:
    if not product_version:
        return None
    try:
        return int(product_version.split(".", 1)[0])
    except (ValueError, IndexError):
        return None


async def _status_async(serial: str | None) -> dict[str, Any]:
    client = await lockdown.create(serial)
    try:
        values = await lockdown.all_values(client)
        major = _major_version(values.get("ProductVersion"))
        # Developer Mode only exists on iOS 16+. Below that, dev-signed apps
        # run without it, so we report it as effectively satisfied.
        if major is not None and major < 16:
            return {
                "supported": False,
                "enabled": True,
                "reason": "Developer Mode not required below iOS 16",
                "product_version": values.get("ProductVersion"),
            }
        try:
            raw = await lockdown.get_value(client, domain=_AMFI_DOMAIN, key="DeveloperModeStatus")
        except Exception as exc:  # noqa: BLE001
            return {
                "supported": True,
                "enabled": None,
                "reason": f"could not read status: {exc}",
                "product_version": values.get("ProductVersion"),
            }
        return {
            "supported": True,
            "enabled": bool(raw),
            "product_version": values.get("ProductVersion"),
        }
    finally:
        await lockdown.close(client)


def status(serial: str | None = None) -> dict[str, Any]:
    """Return Developer Mode status for a device."""
    return run(_status_async(serial))


async def _enable_async(serial: str | None) -> dict[str, Any]:
    from pymobiledevice3.services.amfi import AmfiService

    client = await lockdown.create(serial)
    try:
        service = AmfiService(client)
        await maybe_await(service.enable_developer_mode())
        return {
            "ok": True,
            "note": (
                "The device will reboot. After it restarts, open "
                "Settings > Privacy & Security > Developer Mode, turn it on, "
                "and confirm."
            ),
        }
    finally:
        await lockdown.close(client)


def enable(serial: str | None = None) -> dict[str, Any]:
    """Trigger the Developer Mode enable flow (reboots the device)."""
    return run(_enable_async(serial))
