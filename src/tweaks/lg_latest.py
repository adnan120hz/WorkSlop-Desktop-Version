"""Liquid Glass (Latest) — rollback planner only (feature REMOVED v15).

The "Liquid Glass (Latest)" full-backup payload (the "Liquid Glass
iOS 26.6.1 RC S8" switch) was removed from the product in v15 by user
order (2026-10-10) after the author's own iOS 26.6.1 device test
showed no on-screen effect. Its TweakID is a tombstone
(REMOVED_TWEAK_IDS in src/tweaks/capabilities.py): nothing in the app
can stage or apply it any more.

This module survives for exactly one reason: devices that applied
the payload under v14 still carry its keys, and the Liquid Glass
Disable page's "Roll Back Latest" action must be able to strip them.
What remains is the fresh-capture rollback planner: it reads the
device's CURRENT three files and removes only this payload's keys
(SolariumForceFallback from com.apple.SwiftUI.plist,
SBDisallowGlassTime and SBDisallowGlassButtons from
.GlobalPreferences.plist, SBDisableSpecularEverywhereUsingLSSAssertion
from com.apple.springboard.plist); every other key is kept.

Like ``lg_disable``/``lg_squair``, this module stays free of the
device stack (no ``src.restore`` import): tuple planners only.
"""

import plistlib

from src.exceptions.nugget_exception import NuggetException
from src.tweaks import lg_disable

# --- SwiftUI file ------------------------------------------------------
SWIFTUI_DOMAIN = "HomeDomain"
SWIFTUI_REL_PATH = "Library/Preferences/com.apple.SwiftUI.plist"
SWIFTUI_KEY = lg_disable.GP_KEY  # "SolariumForceFallback"

# --- File A (exactly two keys) ----------------------------------------
GP_KEYS = ("SBDisallowGlassTime", "SBDisallowGlassButtons")
G1_DOMAIN = lg_disable.G1_DOMAIN
G1_REL_PATH = lg_disable.G1_REL_PATH

# --- SpringBoard file ---------------------------------------------------
SB_DOMAIN = "HomeDomain"
SB_REL_PATH = "Library/Preferences/com.apple.springboard.plist"
SB_KEY = "SBDisableSpecularEverywhereUsingLSSAssertion"

# Inject-tuple metadata, identical to what src.restore.lgd_full forces
# for every full-route payload (kept literal: tweak modules must not
# import src.restore).
FILE_MODE = 0o100644  # S_IFREG | 0644
FILE_OWNER = 501
FILE_GROUP = 501

ROLLBACK_NOTE = (
    "Liquid Glass (Latest) rollback: exactly this payload's keys were "
    "removed (SolariumForceFallback from com.apple.SwiftUI.plist, "
    "SBDisallowGlassTime and SBDisallowGlassButtons from "
    ".GlobalPreferences.plist, SBDisableSpecularEverywhereUsingLSSAssertion "
    "from com.apple.springboard.plist); every other key was kept."
)


def _inject_tuple(domain: str, rel_path: str, data: bytes):
    """One full-route inject tuple (mode/owner/group force-stamped)."""
    return (domain, rel_path, bytes(data), FILE_MODE, FILE_OWNER,
            FILE_GROUP)


def _remove_keys(base: dict, keys, label: str) -> bytes:
    """Serialise ``base`` minus exactly ``keys``, round-trip checked."""
    merged = {k: v for k, v in base.items() if k not in keys}
    payload = plistlib.dumps(merged, fmt=plistlib.FMT_BINARY,
                             sort_keys=True)
    if not payload:
        raise ValueError(f"{label}: rollback payload would be empty.")
    parsed = lg_disable.load_plist_dict(payload)
    if parsed != merged:
        raise ValueError(
            f"{label}: rollback payload failed its own round-trip "
            "check.")
    return payload


def plan_latest_rollback_payloads(fresh_gp, fresh_swiftui=None,
                                  fresh_springboard=None):
    """Rollback plan from FRESH device captures.

    Returns ``(payloads, note)``: inject tuples writing each captured
    file back with exactly this payload's keys removed (never a stored
    pre-apply original — the device state may have moved on). A file
    that is absent in the fresh capture yields no tuple: there is
    nothing on the device to remove a key from.
    """
    if not isinstance(fresh_gp, dict):
        raise NuggetException(
            "Liquid Glass (Latest): rollback needs a fresh read of the "
            "device's .GlobalPreferences.plist, and it could not be "
            "read or parsed. Nothing was written.")
    payloads = []
    if isinstance(fresh_swiftui, dict):
        payloads.append(_inject_tuple(
            SWIFTUI_DOMAIN, SWIFTUI_REL_PATH,
            _remove_keys(fresh_swiftui, (SWIFTUI_KEY,),
                         "com.apple.SwiftUI.plist")))
    payloads.append(_inject_tuple(
        G1_DOMAIN, G1_REL_PATH,
        _remove_keys(fresh_gp, GP_KEYS, ".GlobalPreferences.plist")))
    if isinstance(fresh_springboard, dict):
        payloads.append(_inject_tuple(
            SB_DOMAIN, SB_REL_PATH,
            _remove_keys(fresh_springboard, (SB_KEY,),
                         "com.apple.springboard.plist")))
    return payloads, ROLLBACK_NOTE
