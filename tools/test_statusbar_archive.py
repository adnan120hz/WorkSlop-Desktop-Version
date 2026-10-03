#!/usr/bin/env python3
"""Offline test for the iOS 27 StatusBarOverrides.archive (no device needed).

Guards the two things that are easy to break silently:

* the archive we build is a real ``NSKeyedArchiver`` binary plist with the
  class graph SpringBoard unarchives -- ``_SBSystemStatusStatusBarOverrides
  ArchiveRecord`` -> ``STStatusBarData`` -> ``STStatusBarDataCellularEntry``;
* the apply/reset paths stage it in **HomeDomain**, the same domain the iOS 26
  classic statusBarOverrides uses, and the reset writes a *valid empty* record
  (SpringBoard unlinks that itself) instead of poking FeatureFlags.

Also pins the deliberate scope limit: only the carrier names are settable.

Run: python tools/test_statusbar_archive.py
"""
import os
import plistlib
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.tweaks.basic_plist_locations import FileLocation
from src.tweaks.status_bar.statusbar_archive import (
    ARCHIVE_DOMAIN,
    ARCHIVE_PATH,
    MAX_CARRIER_LENGTH,
    build_archive,
    build_reset_archive,
    carrier_names,
    is_reset_archive,
    status_bar_data,
)

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def classname(objects, uid):
    return objects[uid.data].get("$classname")


def cell_entries(payload):
    """Return the cellular entry instances held by an archive."""
    data, objects = status_bar_data(payload)
    entries = []
    for key in ("cellularEntry", "secondaryCellularEntry"):
        uid = data.get(key)
        if isinstance(uid, plistlib.UID):
            entries.append(objects[uid.data])
    return entries


# =============================================================================
def test_is_a_keyed_archive():
    print("\nNSKeyedArchiver container")
    payload = build_archive("Testname", None)
    archive = plistlib.loads(payload)
    check("binary plist", payload.startswith(b"bplist"), payload[:8].decode("latin-1"))
    check("$archiver is NSKeyedArchiver", archive["$archiver"] == "NSKeyedArchiver")
    check("$version is 100000", archive["$version"] == 100000)
    check("$top points at root", isinstance(archive["$top"]["root"], plistlib.UID))
    check("objects start with $null", archive["$objects"][0] == "$null")

    objects = archive["$objects"]
    root = objects[archive["$top"]["root"].data]
    check(
        "root class is the override record",
        classname(objects, root["$class"]) == "_SBSystemStatusStatusBarOverridesArchiveRecord",
    )
    data = objects[root["statusBarData"].data]
    check("statusBarData class", classname(objects, data["$class"]) == "STStatusBarData")
    suppressed = objects[root["suppressedBackgroundActivityIdentifiers"].data]
    check("suppressed set class", classname(objects, suppressed["$class"]) == "NSSet")
    check("suppressed set is empty", suppressed["NS.objects"] == [])


def test_cellular_entry_shape():
    print("\ncellular entry shape")
    payload = build_archive("Testname", "Second")
    entry, secondary = cell_entries(payload)
    objects = plistlib.loads(payload)["$objects"]

    for label, item in (("primary", entry), ("secondary", secondary)):
        check(f"{label} class", classname(objects, item["$class"]) == "STStatusBarDataCellularEntry")
        check(f"{label} enabled", item["enabled"] is True)
        check(f"{label} status is connected", item["status"] == 5)
        check(f"{label} string and crossfadeString share an object",
              item["string"].data == item["crossfadeString"].data)
        check(f"{label} no badge", objects[item["badgeString"].data] == "$null")
        check(f"{label} no suffix", objects[item["suffixString"].data] == "$null")

    check("both entries share one class definition",
          entry["$class"].data == secondary["$class"].data)
    check("names round-trip", carrier_names(payload) == ("Testname", "Second"))


def test_reset_record():
    print("\nreset record")
    payload = build_reset_archive()
    check("is a reset record", is_reset_archive(payload))
    check("carries no names", carrier_names(payload) == (None, None))
    check("has no cellular entries", cell_entries(payload) == [])
    # SpringBoard drops the file itself when the record decodes empty, so the
    # reset must stay structurally valid rather than become a null file.
    root = plistlib.loads(payload)["$objects"][1]
    check("root still a valid record",
          root["$class"] is not None and root["statusBarData"] is not None)


def test_variants():
    print("\nvariants")
    check("primary only", carrier_names(build_archive("A", None)) == ("A", None))
    check("secondary only", carrier_names(build_archive(None, "B")) == (None, "B"))
    check("empty strings are treated as unset", is_reset_archive(build_archive("", "")))
    check("no args is a reset", is_reset_archive(build_archive()))
    check("build_reset_archive matches build_archive()",
          build_reset_archive() == build_archive(None, None))

    long_name = "X" * 200
    primary, _ = carrier_names(build_archive(long_name))
    check("long names are truncated", len(primary) == MAX_CARRIER_LENGTH,
          f"{len(primary)} chars")

    unicode_name = "Билайн"
    check("utf-8 names survive", carrier_names(build_archive(unicode_name))[0] == unicode_name)


def test_rejects_foreign_payloads():
    print("\nrejects non-archive payloads")
    for label, payload in (
        ("random bytes", b"\x00\x01\x02not a plist"),
        ("empty", b""),
        ("plain plist", plistlib.dumps({"hello": "world"})),
    ):
        check(f"{label} is not a reset", is_reset_archive(payload) is False)
        try:
            status_bar_data(payload)
            check(f"{label} raises", False)
        except (ValueError, KeyError, IndexError, TypeError):
            check(f"{label} raises", True)


# =============================================================================
def test_delivery_path():
    print("\ndelivery path")
    from src.restore.path_mapping import split_path_into_domain

    check("enum path matches the writer constant",
          FileLocation.statusBarOverridesArchive.value == "/var/mobile" + ARCHIVE_PATH,
          FileLocation.statusBarOverridesArchive.value)
    domain, rel = split_path_into_domain("/var/mobile" + ARCHIVE_PATH)
    check("resolves to HomeDomain", domain == ARCHIVE_DOMAIN, domain)
    check("relative path is inside Library/SpringBoard",
          rel == "Library/SpringBoard/StatusBarOverrides.archive", rel)

    # The iOS 26 classic file has to land in the same domain, otherwise the
    # restore would need a second mechanism on 27.
    classic_domain, classic_rel = split_path_into_domain("/var/mobile/Library/SpringBoard/statusBarOverrides")
    check("same domain as the iOS 26 classic file", classic_domain == domain)
    check("classic file is not the archive", classic_rel != rel)


# =============================================================================
def test_tweak_stages_the_archive():
    print("\nStatusBarTweak.apply_ios27_tweak")
    try:
        from src.tweaks.status_bar.status_bar_tweak import StatusBarTweak
    except Exception as e:
        # needs the cffi-backed statusBarOverrideData struct; skip when the
        # interpreter has no cffi so this file still runs bare.
        print(f"  skipped: {type(e).__name__}: {e}")
        return

    tweak = StatusBarTweak()
    check("disabled by default", not tweak.enabled)

    files: list = []
    tweak.apply_ios27_tweak(files)
    check("a disabled tweak stages nothing", files == [])

    tweak.set_enabled(True)
    tweak.apply_ios27_tweak(files)
    # Audit B30 (4dff4af): an enabled tweak with no overrides stages
    # nothing — build_archive(None, None) is the *reset* record, and
    # staging it on an empty apply would clobber the user's status bar.
    # Explicit reset still goes through build_reset_archive(). This
    # expectation was stale: the test predates B30 and was never updated.
    check("enabled with no names stages nothing (B30)",
          len(files) == 0)

    tweak.set_carrier_override("MyCarrier")
    tweak.set_secondary_carrier_override("Second")
    files = []
    tweak.apply_ios27_tweak(files)
    check("one file staged", len(files) == 1)
    staged = files[0]
    check("lands in HomeDomain", staged.domain == "HomeDomain", staged.domain)
    check("lands on the archive path",
          staged.restore_path == ARCHIVE_PATH, staged.restore_path)
    check("owned by mobile:mobile",
          (staged.owner, staged.group) == (501, 501),
          f"{staged.owner}:{staged.group}")
    check("carries both carrier names",
          carrier_names(staged.contents) == ("MyCarrier", "Second"))

    # The dead iOS 27 no-op is gone; the iOS 26 classic writer is untouched.
    check("the iOS 27 no-op apply_tweak override is gone",
          "apply_tweak" not in StatusBarTweak.__dict__)
    check("the classic iOS 26 writer still exists",
          callable(getattr(tweak, "apply_classic_tweak", None)))
    classic: list = []
    tweak.apply_classic_tweak(classic)
    check("classic writer still targets the classic file",
          len(classic) == 1
          and classic[0].restore_path == "/Library/SpringBoard/statusBarOverrides"
          and classic[0].domain == "HomeDomain",
          getattr(classic[0], "restore_path", None))


# =============================================================================
test_is_a_keyed_archive()
test_cellular_entry_shape()
test_reset_record()
test_variants()
test_rejects_foreign_payloads()
test_delivery_path()
test_tweak_stages_the_archive()

print(f"\nALL {PASS} CHECKS PASSED")
