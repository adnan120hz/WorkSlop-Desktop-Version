"""Liquid Glass (Latest) — payload core + planner for the newest keys.

One product payload (2026-10-07) riding the existing Liquid Glass
Disable full-backup route (``src/restore/lgd_full.py``). It writes
Apple's real firmware keys — no invented keys — into the files their
readers actually open:

* **SwiftUI file** — ``SolariumForceFallback`` = true in the device's
  own ``com.apple.SwiftUI.plist`` (HomeDomain
  ``Library/Preferences/com.apple.SwiftUI.plist``). Firmware audit S8
  (2026-10-07, grades [FIRMWARE-DUMP]/[XREF]): the key's reader in
  DesignLibrary is ALIVE in iOS 26.6.1 (23G82) — a live
  ``boolForKey:`` on the ``com.apple.SwiftUI`` defaults suite at offset
  0x18b78800c — and equally alive in iOS 26.1 (23B85, 0x18afa6838). The
  file is created lazily by the system and may not exist yet; a missing
  base means the payload creates it. The merge never drops an existing
  key (the same fail-hard diff gate as G1).
* **File A** — ``SBDisallowGlassTime`` + ``SBDisallowGlassButtons`` =
  true merged into the device's own ``.GlobalPreferences.plist``
  (HomeDomain) through the same diff-gated builder as G1/Squair. The
  device base is REQUIRED: without it the plan refuses (fail closed).
* **SpringBoard file** — ``SBDisableSpecularEverywhereUsingLSSAssertion``
  = true merged into the device's own ``com.apple.springboard.plist``
  (HomeDomain ``Library/Preferences/com.apple.springboard.plist``; the
  audit found its reader in that file's suite). The payload bytes are
  NEVER empty: a zero-byte SpringBoard plist risks a boot loop on
  iOS 26.2+, so the builder asserts a non-empty, parseable dict.

Honesty grade: the keys and their readers are firmware-proven (the
SolariumForceFallback reader at code level), but the on-screen effect
is NOT proven — nothing here claims the glass is disabled. Judge it
with an isolated device test.

Like ``lg_disable``/``lg_squair``, this module stays free of the device
stack (no ``src.restore`` import): payload builders + tuple planners
only.
"""

import plistlib

from src.exceptions.nugget_exception import NuggetException
from src.tweaks import lg_disable
from src.tweaks.basic_plist_locations import FileLocation
from src.tweaks.tweak_classes import BasicPlistTweak

FEATURE_NAME = "Liquid Glass (Latest)"

# --- SwiftUI file (the S8 reader home) ------------------------------------
SWIFTUI_DOMAIN = "HomeDomain"
SWIFTUI_REL_PATH = "Library/Preferences/com.apple.SwiftUI.plist"
SWIFTUI_KEY = lg_disable.GP_KEY  # "SolariumForceFallback"
SWIFTUI_KEY_VALUE = True

# --- File A (exactly two keys; real bool true) ----------------------------
GP_KEYS = ("SBDisallowGlassTime", "SBDisallowGlassButtons")
GP_KEY_VALUES = {key: True for key in GP_KEYS}
G1_DOMAIN = lg_disable.G1_DOMAIN
G1_REL_PATH = lg_disable.G1_REL_PATH

# --- SpringBoard file -------------------------------------------------------
SB_DOMAIN = "HomeDomain"
SB_REL_PATH = "Library/Preferences/com.apple.springboard.plist"
SB_KEY = "SBDisableSpecularEverywhereUsingLSSAssertion"
SB_KEY_VALUE = True

# Inject-tuple metadata, identical to what src.restore.lgd_full forces
# for every full-route payload (kept literal: tweak modules must not
# import src.restore).
FILE_MODE = 0o100644  # S_IFREG | 0644
FILE_OWNER = 501
FILE_GROUP = 501

# Honest journal/log notes. Delivery is confirmed by the restore task;
# the on-screen effect is never claimed.
APPLY_NOTE = (
    "Liquid Glass (Latest): the three-file payload was delivered by "
    "the full-backup restore (sent, awaiting reboot). Whether iOS "
    "26.6.1 honors these keys on screen is NOT proven — the "
    "SolariumForceFallback reader is alive in the firmware "
    "[FIRMWARE-DUMP]/[XREF], but the visual effect must be judged by "
    "an isolated device test."
)

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


def _merge(base: dict, inserts: dict, label: str) -> bytes:
    """Merge ``inserts`` into ``base`` through the G1 fail-hard gate.

    ``lg_disable.build_g1_payload`` already refuses to lose or alter a
    single original key; the extra round-trip assert keeps the planner
    honest even if that builder ever changes.
    """
    payload = lg_disable.build_g1_payload(base, inserts)
    parsed = lg_disable.load_plist_dict(payload)
    missing = [k for k in base if k not in parsed]
    if missing:
        raise ValueError(
            f"{label}: merge would drop device keys: {missing!r}")
    for key, value in inserts.items():
        if parsed.get(key) != value or type(parsed.get(key)) is not type(value):
            raise ValueError(
                f"{label}: inserted key {key!r} did not land as "
                f"{value!r}")
    return payload


def build_swiftui_payload(swiftui_base) -> bytes:
    """SwiftUI file payload: base (or {}) + SolariumForceFallback."""
    base = {} if swiftui_base is None else swiftui_base
    if not isinstance(base, dict):
        raise NuggetException(
            "Liquid Glass (Latest): the device's com.apple.SwiftUI.plist "
            "could not be parsed, so it was NOT written. Nothing was "
            "written.")
    return _merge(base, {SWIFTUI_KEY: SWIFTUI_KEY_VALUE},
                  "com.apple.SwiftUI.plist")


def build_springboard_payload(springboard_base) -> bytes:
    """SpringBoard file payload; bytes are NEVER empty (boot safety)."""
    base = {} if springboard_base is None else springboard_base
    if not isinstance(base, dict):
        raise NuggetException(
            "Liquid Glass (Latest): the device's "
            "com.apple.springboard.plist could not be parsed, so it "
            "was NOT written. Nothing was written.")
    payload = _merge(base, {SB_KEY: SB_KEY_VALUE},
                     "com.apple.springboard.plist")
    # Audit rule: a zero-byte com.apple.springboard.plist can crash
    # SpringBoard at boot on iOS 26.2+. The payload must always be a
    # non-empty, parseable plist dict.
    if not payload:
        raise ValueError(
            "com.apple.springboard.plist payload is empty — refusing "
            "to write a zero-byte SpringBoard plist.")
    parsed = lg_disable.load_plist_dict(payload)
    if not isinstance(parsed, dict) or SB_KEY not in parsed:
        raise ValueError(
            "com.apple.springboard.plist payload failed its own "
            "round-trip check.")
    return payload


def plan_latest_apply_payloads(gp_base, swiftui_base=None,
                               springboard_base=None,
                               extra_inserts=None) -> list:
    """Inject tuples for a Latest apply: SwiftUI file + File A + SB file.

    ``gp_base`` MUST be the parsed live device
    ``.GlobalPreferences.plist`` (fail-closed without it, like G1).
    ``swiftui_base`` / ``springboard_base`` may be None (file absent on
    the device) — the payload then creates the file. ``extra_inserts``
    are deliberately staged keys from other routes writing the
    .GlobalPreferences.plist in the same apply pass (e.g. G1's candidate
    key when both routes are enabled): they ride the merge so the later
    whole-file write cannot silently drop them.
    """
    if not isinstance(gp_base, dict):
        raise NuggetException(
            "Liquid Glass (Latest): the full-backup route needs the "
            "device's own .GlobalPreferences.plist as the File A merge "
            "base, and it could not be read. Nothing was written.")
    inserts = dict(GP_KEY_VALUES)
    if extra_inserts:
        inserts.update(extra_inserts)
    file_a = lg_disable.build_g1_payload(gp_base, inserts)
    return [
        _inject_tuple(SWIFTUI_DOMAIN, SWIFTUI_REL_PATH,
                      build_swiftui_payload(swiftui_base)),
        _inject_tuple(G1_DOMAIN, G1_REL_PATH, file_a),
        _inject_tuple(SB_DOMAIN, SB_REL_PATH,
                      build_springboard_payload(springboard_base)),
    ]


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


class LGDLatestTweak(BasicPlistTweak):
    """Staging marker for the Liquid Glass (Latest) payload.

    Like Squair, the whole-file payloads REPLACE device files through
    the full-backup route, so staging is a surgical merge into the
    device's live files (bases armed by DeviceManager's prepare step).
    This tweak NEVER stages through the generic sparse pass: the SwiftUI
    and SpringBoard payloads can only ride the full-backup route, so
    ``apply_tweak`` marks ``staged`` (armed + enabled) and leaves
    ``other_tweaks`` untouched; DeviceManager diverts the marker into a
    gated full-route run. With no live .GlobalPreferences base it stages
    nothing (fail closed), exactly like the armed-G1 contract.
    """

    def __init__(self):
        super().__init__(FileLocation.globalPreferencesHomeDomain,
                         GP_KEYS[0], value=True)
        self.staged = False
        self._lgd_gp_base = None
        self._lgd_swiftui_base = None
        self._lgd_springboard_base = None

    def apply_tweak(self, other_tweaks: dict) -> dict:
        if not self.enabled:
            self.staged = False
            return other_tweaks
        if not isinstance(self._lgd_gp_base, dict):
            # No live device base armed this pass → fail closed:
            # nothing is staged and the full route is never invoked.
            self.staged = False
            return other_tweaks
        # Validate all three merges NOW (fail-hard diff gate) so a bad
        # base surfaces at staging time, not mid-restore. The route
        # re-plans from the same bases and verifies the injected bytes.
        plan_latest_apply_payloads(
            self._lgd_gp_base, self._lgd_swiftui_base,
            self._lgd_springboard_base)
        self.staged = True
        return other_tweaks
