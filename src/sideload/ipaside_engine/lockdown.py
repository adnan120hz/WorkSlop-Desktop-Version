"""Lockdown client helpers.

Centralizes how the engine opens a lockdown connection to a device so every
feature (device info, developer mode, app install) shares the same
connection-selection policy: prefer USB, fall back to network.
"""

from __future__ import annotations

import os
from typing import Any

from ._asyncutil import maybe_await
from .errors import EngineError

#: Environment variable naming the transport to use: ``usb``, ``wifi``, or unset.
CONNECTION_ENV = "IPASIDE_CONNECTION"


def preferred_connection() -> str | None:
    """The transport the user picked, or None to prefer USB and fall back.

    Read from the environment rather than threaded through every command because
    the choice applies to all of them equally, and the ``serve`` protocol already
    scopes env per request and restores it afterwards - the same route the Apple ID
    password takes. Values are accepted loosely because a person may type them.
    """
    raw = (os.environ.get(CONNECTION_ENV) or "").strip().lower()
    if raw in ("", "auto"):
        return None
    if raw == "usb":
        return "USB"
    if raw in ("network", "wifi", "wi-fi"):
        return "Network"
    raise EngineError(
        f"{CONNECTION_ENV}={raw!r} is not a transport; use usb, wifi, or auto."
    )


async def create(serial: str | None = None, prefer_usb: bool = True) -> Any:
    """Open a lockdown client for a device.

    ``serial`` selects a specific UDID; ``None`` means "the connected device", which
    is resolved here rather than handed to usbmux as a blank. usbmux would answer a
    blank with whichever device it happens to list first, so with two phones attached
    every command - app list, install, uninstall - would silently act on an arbitrary
    one. Resolving up front makes that an error instead (see ``device.resolve_serial``).

    When ``prefer_usb`` is set we try USB first (more reliable for installs)
    and transparently fall back to any transport (e.g. Wi-Fi) if USB is absent.
    """
    from pymobiledevice3.lockdown import create_using_usbmux

    from . import device  # deferred: device imports this module at load time

    serial = await device.resolve_serial_async(serial)
    forced = preferred_connection()
    if forced is not None:
        # An explicit choice is honoured rather than treated as a hint: quietly
        # using the other transport would make the setting a lie, and would hide a
        # bad cable behind a slow Wi-Fi install.
        attempts: tuple[str | None, ...] = (forced,)
    else:
        # USB first: on the test device a lockdown value read took 132ms over USB
        # against 575ms over the network, and it is the more reliable for installs.
        attempts = ("USB", None) if prefer_usb else (None,)
    last: Exception | None = None
    for connection_type in attempts:
        try:
            return await maybe_await(
                create_using_usbmux(serial=serial, connection_type=connection_type)
            )
        except Exception as exc:  # this transport is unavailable - try the next
            last = exc
    raise device.DeviceError(_unreachable(serial, last, forced)) from last


def _unreachable(serial: str, cause: Exception | None, forced: str | None) -> str:
    """Why a known device could not be reached, in words worth showing a person.

    The device was named, so this is not ambiguity - it is a phone that is gone,
    locked, or not trusted. Worth translating because ``DeviceNotFoundError``
    used to stringify blank (an empty banner) and still should not leak the
    library wording into the UI: the user gets a reconnect sentence.
    """
    from pymobiledevice3.exceptions import DeviceNotFoundError

    if forced is not None:
        # The phone may well be attached, just not the way it was told to use, so
        # saying "not connected" would send the user looking for the wrong thing.
        wording = "over USB" if forced == "USB" else "over Wi-Fi"
        return (
            f"Device {serial} is not reachable {wording}. Connect it that way, or "
            "set the connection back to Automatic."
        )
    if isinstance(cause, DeviceNotFoundError):
        return (
            f"Device {serial} is not connected. Reconnect it, or pick another device."
        )
    detail = str(cause) if cause is not None and str(cause) else type(cause).__name__
    return (
        f"Could not reach device {serial}: {detail}. "
        "Check it is plugged in, unlocked, and trusted."
    )


async def all_values(client: Any) -> dict[str, Any]:
    """Return the device's lockdown value bag as a plain dict."""
    values = await maybe_await(getattr(client, "all_values", {}))
    return values if isinstance(values, dict) else {}


async def get_value(client: Any, domain: str | None = None, key: str | None = None) -> Any:
    """Read a single lockdown value, optionally scoped to a domain."""
    return await maybe_await(client.get_value(domain=domain, key=key))


async def close(client: Any) -> None:
    """Close a lockdown client, awaiting if needed."""
    await maybe_await(client.close())
