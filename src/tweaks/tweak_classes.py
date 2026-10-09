import logging
import re
from typing import Optional, Callable

from PySide6.QtCore import QCoreApplication

from .basic_plist_locations import FileLocation
from src.exceptions.nugget_exception import NuggetException

_on_tweak_change: Optional[Callable[[], None]] = None

def set_tweak_change_callback(callback: Optional[Callable[[], None]]):
    """Register a callback to be invoked when any tweak changes."""
    global _on_tweak_change
    _on_tweak_change = callback

def _notify_tweak_change():
    if _on_tweak_change:
        try:
            _on_tweak_change()
        except Exception:
            pass  # Never let callback errors break tweak changes


def merge_disabled_plist(existing, incoming: dict) -> dict:
    """Single deterministic owner for the launchd disabled.plist merge.

    Audit 38: ``com.apple.thermalmonitord`` had two writers — the
    registry ``Disable Thermal`` BasicPlistTweak and the Daemons
    AdvancedPlistTweak (``Daemon.thermalmonitord``). Both wrote the
    same key into ``FileLocation.disabledDaemons`` with plain
    last-write-wins assignment / ``dict.update``, so the staged
    result depended on apply order (a ``False`` from Daemons applied
    last silently re-enabled a daemon that Disable Thermal had
    asked to disable, and vice-versa).

    This helper is now the ONLY code path that merges values into
    a staged ``disabled.plist`` dict. Both plist tweak classes route
    their ``disabledDaemons`` writes through it. Bool values combine
    with logical OR — a daemon ends up disabled if EITHER writer
    requests it — so the final dict (and its plist bytes) is
    identical regardless of apply order. To re-enable a daemon the
    user must turn off both toggles that can request it.
    """
    merged = dict(existing) if isinstance(existing, dict) else {}
    for key, value in incoming.items():
        if key in merged and isinstance(merged[key], bool) and isinstance(value, bool):
            merged[key] = merged[key] or value
        else:
            merged[key] = value
    return merged


# ---------------------------------------------------------------------------
# Fix Audit 30: deterministic owner for the shared resolution plist.
#
# ``FileLocation.resolution`` has two writers staging the SAME canvas keys
# (``canvas_width`` / ``canvas_height``): Risky CustomResolution (an
# ``AdvancedPlistTweak`` whose values the user typed explicitly) and
# ``RdarFixTweak`` (model-derived dimensions for the Dynamic Island status
# bar fix). Plain dict assignment made the winner depend on apply order —
# whichever ran last silently won, and RdarFix's "Revert" popped the keys
# even when they belonged to CustomResolution.
#
# Written priority rule (the ONLY rule; both writers route through the
# helpers below, following the Audit 38/93 single-merge-owner pattern):
#
#   1. CustomResolution wins over RdarFix for every shared canvas key —
#      an explicit user-entered dimension outranks a derived fix value,
#      regardless of which tweak applies first.
#   2. Within one writer, the later value wins (only reachable when the
#      same tweak stages twice in one pass).
#   3. RdarFix "Revert" (``di_type == -1``) removes only canvas keys
#      RdarFix itself staged; CustomResolution's keys survive a revert.
#   4. Every collision is logged with key, location, both writers and
#      the declared winner — never resolved silently.
#
# Provenance travels on the staged dict itself (``_ResolutionPlist`` is a
# plain ``dict`` for plist purposes; the sources map is an attribute,
# never a plist key), so the rule holds in either apply order.
# ---------------------------------------------------------------------------
_RESOLUTION_CANVAS_KEYS = ("canvas_width", "canvas_height")
_RESOLUTION_WRITER_PRIORITY = {"CustomResolution": 2, "RdarFix": 1}

_resolution_log = logging.getLogger("WorkSlop.apply.resolution")


class _ResolutionPlist(dict):
    """A staged resolution plist plus which writer staged each canvas key."""

    _canvas_sources: dict


def _as_resolution_plist(existing) -> _ResolutionPlist:
    plist = _ResolutionPlist(existing) if isinstance(existing, dict) else _ResolutionPlist()
    plist._canvas_sources = dict(getattr(existing, "_canvas_sources", {}) or {})
    return plist


def merge_resolution_canvas(existing, incoming: dict, *, source: str) -> _ResolutionPlist:
    """Merge ``incoming`` into the shared resolution plist deterministically.

    Implements the Fix Audit 30 priority rule above and logs every
    shared-canvas-key collision with its declared winner.
    """
    plist = _as_resolution_plist(existing)
    sources = plist._canvas_sources
    for key, value in incoming.items():
        if key in _RESOLUTION_CANVAS_KEYS and key in plist:
            previous = sources.get(key, "unknown")
            if _RESOLUTION_WRITER_PRIORITY.get(source, 0) >= \
                    _RESOLUTION_WRITER_PRIORITY.get(previous, 0):
                winner, loser = source, previous
                plist[key] = value
                sources[key] = source
            else:
                winner, loser = previous, source
            _resolution_log.warning(
                "[ApplyOrder] resolution canvas conflict: key=%r "
                "location=%s writers=%s winner=%s (Fix Audit 30 priority: "
                "CustomResolution > RdarFix, regardless of apply order)",
                key, FileLocation.resolution.value,
                sorted({previous, source}), winner)
        else:
            plist[key] = value
            if key in _RESOLUTION_CANVAS_KEYS:
                sources[key] = source
    return plist


def revert_resolution_canvas(existing) -> _ResolutionPlist:
    """RdarFix revert: drop only the canvas keys RdarFix itself staged.

    Keys staged by CustomResolution (higher priority, explicit user
    values) survive, and keeping them is logged — the old behaviour
    popped both keys blindly, silently deleting a CustomResolution the
    user had enabled in the same pass.
    """
    plist = _as_resolution_plist(existing)
    sources = plist._canvas_sources
    for key in _RESOLUTION_CANVAS_KEYS:
        if key not in plist:
            continue
        owner = sources.get(key)
        if owner == "CustomResolution":
            _resolution_log.warning(
                "[ApplyOrder] RdarFix revert kept key=%r location=%s: "
                "staged by CustomResolution, which outranks RdarFix "
                "(Fix Audit 30 priority rule)",
                key, FileLocation.resolution.value)
            continue
        plist.pop(key, None)
        sources.pop(key, None)
    return plist

class Tweak:
    def __init__(
            self,
            key: str,
            value: any = 1,
            owner: int = 501, group: int = 501
        ):
        self.key = key
        self.value = value
        self.owner = owner
        self.group = group
        self.enabled = False

    def set_enabled(self, value: bool):
        if self.enabled != value:
            self.enabled = value
            _notify_tweak_change()
    def set_value(self, new_value: any, toggle_enabled: bool = True):
        self.value = new_value
        if toggle_enabled:
            self.enabled = True
        _notify_tweak_change()

    def apply_tweak(self):
        raise NotImplementedError
    
class NullifyFileTweak(Tweak):
    def __init__(
            self,
            file_location: FileLocation,
            owner: int = 501, group: int = 501
        ):
        super().__init__(key=None, value=None, owner=owner, group=group)
        self.file_location = file_location

    def apply_tweak(self, other_tweaks: dict):
        if self.enabled:
            other_tweaks[self.file_location] = b""
    

class BasicPlistTweak(Tweak):
    def __init__(
            self,
            file_location: FileLocation,
            key: str,
            value: any = True,
            owner: int = 501, group: int = 501
        ):
        super().__init__(key=key, value=value, owner=owner, group=group)
        self.file_location = file_location

    def apply_tweak(self, other_tweaks: dict) -> dict:
        if not self.enabled:
            return other_tweaks
        if self.file_location == FileLocation.disabledDaemons:
            # Audit 38: route through the single disabled.plist owner
            # so a shared key (com.apple.thermalmonitord) resolves by
            # logical OR, never by apply order.
            other_tweaks[self.file_location] = merge_disabled_plist(
                other_tweaks.get(self.file_location),
                {self.key: self.value})
        elif self.file_location in other_tweaks:
            other_tweaks[self.file_location][self.key] = self.value
        else:
            other_tweaks[self.file_location] = {self.key: self.value}
        return other_tweaks

class AdvancedPlistTweak(BasicPlistTweak):
    def __init__(
        self,
        file_location: FileLocation,
        keyValues: dict,
        owner: int = 501, group: int = 501,
        never_enable: Optional[set] = None,
        allowed_keys: Optional[set] = None
    ):
        super().__init__(file_location=file_location, key=None, value=keyValues, owner=owner, group=group)
        self.never_enable = set(never_enable or ())
        # If set, only keys in this set are ever applied / stored (interface-
        # visible daemons). Keys outside it are dropped, never written.
        self.allowed_keys = set(allowed_keys) if allowed_keys is not None else None

    def _filter_keys(self, values: dict) -> dict:
        """Drop keys that are hard-protected or not interface-visible."""
        out = {}
        for key, value in values.items():
            if key in self.never_enable:
                continue
            if self.allowed_keys is not None and key not in self.allowed_keys:
                continue
            out[key] = value
        return out

    def set_multiple_values(self, keys: list[str], value: any):
        for key in keys:
            if value and value is not False and value is not None and key in self.never_enable:
                continue  # hard-protected: this key must never be enabled
            if self.allowed_keys is not None and key not in self.allowed_keys:
                continue  # not exposed in the UI: never introduce it
            self.value[key] = value
        _notify_tweak_change()

    def apply_tweak(self, other_tweaks: dict) -> dict:
        if not self.enabled:
            return other_tweaks
        # Merge into any existing payload for this file (e.g. the registry
        # "Disable Thermal" BasicPlistTweak writes one key into the same
        # launchd disabled.plist). Replacing the dict used to silently
        # erase the other writer's keys depending on apply order.
        # Audit 38: for disabled.plist both writers go through the
        # single merge_disabled_plist owner (logical OR for bools), so
        # the shared thermalmonitord key is order-independent.
        existing = other_tweaks.get(self.file_location)
        filtered = self._filter_keys(self.value)
        if self.file_location == FileLocation.disabledDaemons:
            other_tweaks[self.file_location] = merge_disabled_plist(existing, filtered)
        elif self.file_location == FileLocation.resolution:
            # Fix Audit 30: the resolution plist is shared with
            # RdarFixTweak over the same canvas keys — route through
            # the deterministic merge owner so CustomResolution's
            # explicit values win in either apply order (and the
            # collision is logged, never silent).
            other_tweaks[self.file_location] = merge_resolution_canvas(
                existing, filtered, source="CustomResolution")
        else:
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged.update(filtered)
            other_tweaks[self.file_location] = merged
        return other_tweaks


# ---------------------------------------------------------------------------
# RdarFixTweak — ported verbatim from leminlimez/Nugget
# (src/tweaks/tweak_classes.py). Resolution fix for the Dynamic Island status
# bar on certain models; driven by the MobileGestalt page (di_type follows the
# Dynamic Island dropdown selection).
# ---------------------------------------------------------------------------
class RdarFixTweak(BasicPlistTweak):
    def __init__(self):
        super().__init__(file_location=FileLocation.resolution, key=None)
        self.mode = 0
        self.di_type = -1

    def get_rdar_mode(self, model: str) -> int:
        if (model == "iPhone11,2" or model == "iPhone11,4" or model == "iPhone11,6"
            or model == "iPhone11,8"
            or model == "iPhone12,1" or model == "iPhone12,3" or model == "iPhone12,5"):
            self.mode = 1
        elif (model == "iPhone13,2" or model == "iPhone13,3" or model == "iPhone13,4"
              or model == "iPhone14,5" or model == "iPhone14,2" or model == "iPhone14,3"
              or model == "iPhone14,7" or model == "iPhone14,8" or model == "iPhone17,5"):
            self.mode = 2
        elif (model == "iPhone12,8" or model == "iPhone14,6"):
            self.mode = 3
        return self.mode

    def get_rdar_title(self) -> str:
        if self.mode == 1 or self.mode == 3:
            if self.di_type == -1:
                return QCoreApplication.tr("Revert RDAR fix")
            return QCoreApplication.tr("RDAR Fix")
        elif self.mode == 2:
            if self.di_type == -1:
                return QCoreApplication.tr("Revert Status Bar Fix")
            return QCoreApplication.tr("Dynamic Island Status Bar Fix")
        return "hide"

    def set_di_type(self, type: int):
        self.di_type = type

    def apply_tweak(self, other_tweaks: dict, risky_allowed: bool = False) -> dict:
        if not self.enabled:
            return other_tweaks
        # B5 FIX: merge into the existing payload for this file instead of
        # replacing it. FileLocation.resolution is shared with CustomResolution
        # (Risky) — a blind replace meant last-write-wins with the loser's
        # keys silently dropped. Revert no longer writes the old verbatim
        # {"nugget": 0} junk dict (it destroyed the whole plist); it now
        # removes only the canvas keys this tweak owns, keeping anything else
        # in the file. NOTE: this intentionally deviates from the verbatim
        # Nugget port — Nugget's revert destroyed the file (HIGH bug B5).
        # Fix Audit 30: the shared canvas keys now resolve through the
        # deterministic merge owner above — CustomResolution (explicit
        # user values) outranks RdarFix in either apply order, every
        # collision is logged with its winner, and a revert drops only
        # the keys RdarFix itself staged.
        existing = other_tweaks.get(self.file_location)
        if self.di_type == -1:
            # revert the fix: drop our keys, keep the rest of the file
            other_tweaks[self.file_location] = revert_resolution_canvas(existing)
            return other_tweaks
        plist = _as_resolution_plist(existing)
        if self.mode == 1:
            # iPhone XR, XS, and 11
            plist = merge_resolution_canvas(
                plist, {"canvas_height": 1791, "canvas_width": 828},
                source="RdarFix")
        elif self.mode == 3:
            # iPhone SEs
            plist = merge_resolution_canvas(
                plist, {"canvas_height": 1779, "canvas_width": 1000},
                source="RdarFix")
        elif self.mode == 2:
            # Status bar fix (iPhone 12+)
            width = 2868
            height = 1320
            if self.di_type == 2556:
                width = 1179
                height = 2556
            elif self.di_type == 2796:
                width = 1290
                height = 2796
            elif self.di_type == 2622:
                width = 1206
                height = 2622
            elif self.di_type == 2868:
                width = 1320
                height = 2868
            elif self.di_type == 2736:
                width = 1260
                height = 2736
            plist = merge_resolution_canvas(
                plist, {"canvas_height": height, "canvas_width": width},
                source="RdarFix")
        other_tweaks[self.file_location] = plist
        return other_tweaks


# ---------------------------------------------------------------------------
# MobileGestalt tweaks — ported verbatim from leminlimez/Nugget
# (src/tweaks/tweak_classes.py). These write into the "CacheExtra" dict of the
# device's com.apple.MobileGestalt.plist. Per Nugget upstream: not supported
# on iOS 26.2+, never will be.
# ---------------------------------------------------------------------------
class MobileGestaltTweak(Tweak):
    def __init__(
            self,
            key: str, subkey: str = None,
            value: any = 1,
            owner: int = 501, group: int = 501
        ):
        super().__init__(key, value, owner, group)
        self.subkey = subkey

    def apply_tweak(self, plist: dict):
        if not self.enabled:
            return plist
        new_value = self.value
        if self.subkey == None:
            plist["CacheExtra"][self.key] = new_value
        else:
            plist["CacheExtra"][self.key][self.subkey] = new_value
        return plist

class MobileGestaltPickerTweak(Tweak):
    def __init__(
            self,
            key: str, subkey: str = None,
            values: list = [1]
        ):
        super().__init__(key=key, value=values)
        self.subkey = subkey
        self.selected_option = 0 # index of the selected option

    def apply_tweak(self, plist: dict):
        if not self.enabled or self.value[self.selected_option] == "Placeholder":
            return plist
        new_value = self.value[self.selected_option]
        if self.subkey == None:
            plist["CacheExtra"][self.key] = new_value
        else:
            plist["CacheExtra"][self.key][self.subkey] = new_value
            if self.subkey == "ArtworkDeviceSubType":
                plist["CacheExtra"]["YlEtTtHlNesRBMal1CqRaA"] = 1
        return plist

    def set_selected_option(self, new_option: int, is_enabled: bool = True):
        self.selected_option = new_option
        self.enabled = is_enabled

    def get_selected_option(self) -> int:
        return self.selected_option

class MobileGestaltMultiTweak(Tweak):
    def __init__(self, keyValues: dict):
        super().__init__(key=None)
        self.keyValues = keyValues
        # key values looks like ["key name" = value]

    def apply_tweak(self, plist: dict):
        if not self.enabled:
            return plist
        for key in self.keyValues:
            plist["CacheExtra"][key] = self.keyValues[key]
        return plist

class MobileGestaltCacheDataTweak(Tweak):
    def __init__(self, slice_start: int, slice_length: int):
        super().__init__(key=None)
        self.slice_start = slice_start
        self.slice_len = slice_length

    def apply_tweak(self, plist: dict):
        if not self.enabled:
            return plist
        data = bytes(plist["CacheData"]).hex().lower()
        failed_str = QCoreApplication.tr("Failed to enable iPadOS:") + "\n"
        if len(data) <= self.slice_start:
            raise NuggetException(failed_str + QCoreApplication.tr("CacheData is too short!"))
        # skip the padding and get the last 2 bytes for every instance to find the offset
        pattern = re.compile(r"0+(?:5555)*([0-9a-f]{4})")
        offset = None
        value = None
        for match in pattern.finditer(data[self.slice_start : self.slice_start + self.slice_len]):
            value = match.group(1)
            if sum(c != "0" for c in value) >= 3:
                offset = self.slice_start + match.start(1)
                break

        # Error handling
        # Thanks Huy for the extra checks
        if offset is None:
            raise NuggetException(failed_str + QCoreApplication.tr("Pattern not found in CacheData."))
        # Check the extrema offsets
        roffset = offset + 13
        loffset = offset - 67 # real
        if roffset >= len(data) - 1 or roffset - 1 < 0:
            raise NuggetException(
                failed_str + QCoreApplication.tr("Right offset out of range.")
                + f'\nRight Offset: {roffset}, Data Length: {len(data)}'
            )
        if loffset <= 0 or loffset + 1 >= len(data):
            raise NuggetException(
                failed_str + QCoreApplication.tr("Left offset out of range.")
                + f'\nLeft Offset: {loffset}, Data Length: {len(data)}'
            )

        for side_offset in [roffset, loffset]:
            offset_name = "Right" if side_offset == roffset else "Left"
            # check valid values
            if data[side_offset] not in ('1', '3'):
                err_msg: str = QCoreApplication.tr("Value at %SIDE offset is not 1 or 3.")
                raise NuggetException(
                    failed_str + err_msg.replace("%SIDE", offset_name.lower())
                    + f'\nValue[{side_offset}] = {data[side_offset]}, Data Length: {len(data)}'
                )
            # check neighboring values
            if data[side_offset - 1] != '0' or data[side_offset + 1] != '0':
                err_msg: str = QCoreApplication.tr("Values of %SIDE offset neighbors are not 0.")
                raise NuggetException(
                    failed_str + err_msg.replace("%SIDE", offset_name.lower())
                    + f'\nValue[{side_offset-1}] = {data[side_offset - 1]}, Value[{side_offset+1}] = {data[side_offset + 1]}, Data Length: {len(data)}'
                )

        # Set the value of the left offset to 3 to enable iPadOS
        data_list = list(data)
        data_list[loffset] = "3"
        data = "".join(data_list)
        plist["CacheData"] = bytes.fromhex(data)
        return plist


# ---------------------------------------------------------------------------
# FeatureFlagTweak — ported verbatim from leminlimez/Nugget
# (src/tweaks/tweak_classes.py). Writes into the "Global.plist" feature flags
# file (/var/preferences/FeatureFlags/Global.plist). Removed by GoldenNugget,
# re-added here per user request using Nugget's original code.
# ---------------------------------------------------------------------------
class FeatureFlagTweak(Tweak):
    def __init__(
            self,
                flag_category: str, flag_names: list,
                is_list: bool=True, inverted: bool=False
            ):
        super().__init__(key=None)
        self.flag_category = flag_category
        self.flag_names = flag_names
        self.is_list = is_list
        self.inverted = inverted

    def apply_tweak(self, other_tweaks: dict) -> dict:
        # B6 FIX: never write flags for a disabled tweak. Without this guard
        # every Apply rewrote Global.plist even when the user turned the
        # switch off (the old code had no enabled check at all).
        if not self.enabled:
            return other_tweaks
        to_enable = self.enabled
        if self.inverted:
            to_enable = not self.enabled
        # create the category list if it doesn't exist
        if not self.flag_category in other_tweaks:
            other_tweaks[self.flag_category] = {}
        for flag in self.flag_names:
            if self.is_list:
                other_tweaks[self.flag_category][flag] = {
                    'Enabled': to_enable
                }
            else:
                other_tweaks[self.flag_category][flag] = to_enable
        return other_tweaks
