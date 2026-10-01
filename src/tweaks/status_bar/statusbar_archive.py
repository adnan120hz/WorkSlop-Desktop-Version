"""iOS 27+ ``StatusBarOverrides.archive`` writer.

Starting with iOS 27 SpringBoard no longer reads the classic binary
``statusBarOverrides`` struct (and the ``SpeakeasyNewStatusBar`` feature flag
in ``FeatureFlags/Settings.plist`` cannot be written by a restore at all).
Instead it unarchives an ``NSKeyedArchiver`` binary property list from
``/var/mobile/Library/SpringBoard/StatusBarOverrides.archive``:

    _SBSystemStatusStatusBarOverridesArchiveRecord
      +-- statusBarData : STStatusBarData
      |     +-- cellularEntry          : STStatusBarDataCellularEntry
      |     +-- secondaryCellularEntry : STStatusBarDataCellularEntry
      +-- suppressedBackgroundActivityIdentifiers : NSSet (empty)

The file lives in **HomeDomain**, the same domain the iOS 26 classic path
writes, so it is delivered by the normal backup restore -- no exploit and no
out-of-band channel is involved.

Scope: only the carrier **names** are user-settable. Everything else in the
cellular entry is written with fixed values chosen to form a structurally
valid record (round-trip verified offline only -- on-device rendering is
UNVERIFIED, like every other tweak in this repo until a real-device test).

Intended failure mode (also UNVERIFIED on-device): when the record decodes
empty SpringBoard is expected to remove the file itself and the stock carrier
names come back, so a rejected archive should degrade to "no override"
instead of a broken status bar.

Pure stdlib on purpose -- ``src.tweaks`` is imported by the tweak loader and
must not drag in the pymobiledevice3-backed ``src.restore`` package.
"""

import plistlib

# HomeDomain path of the archive, relative to /var/mobile.
ARCHIVE_PATH = "/Library/SpringBoard/StatusBarOverrides.archive"
ARCHIVE_DOMAIN = "HomeDomain"

# The record refuses to render anything longer, so cut here rather than let
# SpringBoard silently drop the whole override.
MAX_CARRIER_LENGTH = 64

_RECORD_CLASS = "_SBSystemStatusStatusBarOverridesArchiveRecord"
_CELLULAR_CLASS = "STStatusBarDataCellularEntry"
_CELLULAR_CLASS_CHAIN = [
    "STStatusBarDataCellularEntry",
    "STStatusBarDataNetworkEntry",
    "STStatusBarDataIntegerEntry",
    "STStatusBarDataEntry",
    "NSObject",
]

# Fixed cellular-entry values. `status` 5 is "connected" and `enabled` true
# is what makes the entry render at all; `displayValue` is the signal-bar
# count and `type` the network-type enum (10 == 5G). The carrier name itself
# is supplied through `string`/`crossfadeString`.
_ENTRY_DEFAULTS = {
    "badgeString": None,
    "callForwardingEnabled": False,
    "displayRawValue": 0,
    "displayValue": 4,
    "enabled": True,
    "isBootstrapCellular": False,
    "lowDataModeActive": False,
    "numberSharingState": 0,
    "rawValue": 0,
    "showsSOSWhenDisabled": False,
    "sosAvailable": False,
    "status": 5,
    "suffixString": None,
    "type": 10,
    "wifiCallingEnabled": False,
}


def _class_def(classname, chain):
    return {"$classes": list(chain), "$classname": classname}


def _truncate(name):
    if not name:
        return None
    name = str(name)[:MAX_CARRIER_LENGTH]
    return name or None


def build_archive(primary_carrier=None, secondary_carrier=None) -> bytes:
    """Build the ``StatusBarOverrides.archive`` payload.

    With no carrier names this returns the *reset* record: a structurally
    valid archive whose status-bar data carries no cellular entries, which
    SpringBoard decodes as "no overrides" and then unlinks.
    """
    primary = _truncate(primary_carrier)
    secondary = _truncate(secondary_carrier)

    objects = ["$null"]

    def add(value):
        objects.append(value)
        return plistlib.UID(len(objects) - 1)

    # Laid out the way the stock archiver writes it: root and status-bar data
    # first, then the payload objects, then every class definition, and the
    # NSSet instance last. Object order carries no meaning to the unarchiver,
    # but matching it keeps our bytes diffable against a real device dump.
    data_class = {}
    data_obj = {"$class": None}
    root_obj = {
        "$class": None,
        "statusBarData": None,
        "suppressedBackgroundActivityIdentifiers": None,
    }
    root = add(root_obj)
    data_uid = add(data_obj)
    root_obj["statusBarData"] = data_uid

    def add_cellular(carrier):
        # `string` and `crossfadeString` reference one shared string object,
        # the same way the stock archiver deduplicates them.
        text = add(carrier)
        entry = {"$class": None}
        for key, value in _ENTRY_DEFAULTS.items():
            entry[key] = plistlib.UID(0) if value is None else value
        entry["string"] = text
        entry["crossfadeString"] = text
        return add(entry)

    entries = []
    if primary:
        entry_uid = add_cellular(primary)
        data_obj["cellularEntry"] = entry_uid
        entries.append(entry_uid)
    if secondary:
        entry_uid = add_cellular(secondary)
        data_obj["secondaryCellularEntry"] = entry_uid
        entries.append(entry_uid)

    if entries:
        # one shared class definition for both cellular entries
        cell_class = add(_class_def(_CELLULAR_CLASS, _CELLULAR_CLASS_CHAIN))
        for entry_uid in entries:
            objects[entry_uid.data]["$class"] = cell_class
    data_obj["$class"] = add(_class_def("STStatusBarData", ["STStatusBarData", "NSObject"]))
    set_class = add(_class_def("NSSet", ["NSSet", "NSObject"]))
    root_obj["$class"] = add(_class_def(_RECORD_CLASS, [_RECORD_CLASS, "NSObject"]))
    root_obj["suppressedBackgroundActivityIdentifiers"] = add({"$class": set_class, "NS.objects": []})

    return plistlib.dumps({
        "$archiver": "NSKeyedArchiver",
        "$version": 100000,
        "$top": {"root": plistlib.UID(root.data)},
        "$objects": objects,
    }, fmt=plistlib.FMT_BINARY)


def build_reset_archive() -> bytes:
    """Archive with no cellular entries -- clears any applied carrier name."""
    return build_archive(None, None)


def status_bar_data(payload: bytes):
    """Return the decoded ``STStatusBarData`` instance of an archive.

    Follows ``$top.root`` -> ``statusBarData`` the same way SpringBoard's
    unarchiver does. Raises ``ValueError`` if the payload is not a usable
    status-bar override archive.
    """
    archive = plistlib.loads(payload)
    if archive.get("$archiver") != "NSKeyedArchiver":
        raise ValueError("not an NSKeyedArchiver payload")
    objects = archive["$objects"]
    root = objects[archive["$top"]["root"].data]
    if objects[root["$class"].data]["$classname"] != _RECORD_CLASS:
        raise ValueError("unexpected root class")
    data = objects[root["statusBarData"].data]
    if objects[data["$class"].data]["$classname"] != "STStatusBarData":
        raise ValueError("unexpected statusBarData class")
    return data, objects


def carrier_names(payload: bytes):
    """Return ``(primary, secondary)`` carrier names held by an archive."""
    data, objects = status_bar_data(payload)

    def read(key):
        uid = data.get(key)
        if not isinstance(uid, plistlib.UID):
            return None
        entry = objects[uid.data]
        if not isinstance(entry, dict):
            return None
        string = entry.get("string")
        if not isinstance(string, plistlib.UID):
            return None
        value = objects[string.data]
        return value if isinstance(value, str) else None

    return read("cellularEntry"), read("secondaryCellularEntry")


def is_reset_archive(payload: bytes) -> bool:
    """True when the payload carries no cellular entries."""
    try:
        data, _ = status_bar_data(payload)
    except (ValueError, KeyError, IndexError, TypeError):
        return False
    return not any(key in data for key in ("cellularEntry", "secondaryCellularEntry"))
