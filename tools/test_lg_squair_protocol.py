#!/usr/bin/env python3
"""Offline tests for the Squair Protocol (test) payload.

Pins the test-only payload contract (see src/tweaks/lg_squair.py):

* the registry carries one switch, LGDisableSquairTest, in the Liquid
  Glass Disable section, built by its own factory (the Beta 1 G1/G2
  entries left the product in v14.0 — their IDs are removed
  tombstones with no spec);
* File Domain bytes are the exact XML plist
  {"SpringBoard": {"SolariumElasticHUD": {"Enabled": bool false}}}
  (sort_keys; no DevelopmentPhase, no integer 0);
* inject tuples force the same metadata as every full-route payload
  (regular 0644, owner/group 501/501);
* the File A merge keeps 100% of the device's original keys and adds
  exactly the two Squair keys as real bool true (diff gate clean), and
  refuses to plan without a device base;
* rollback plans from a FRESH capture: exactly the two keys are removed,
  every other key survives, and the Domain file is NOT in the rollback
  payloads (it cannot be removed by a restore);
* the tweak stages nothing through the sparse dict and fails closed
  without an armed base;
* directory-row donor selection prefers the SAME domain: with a
  HomeDomain directory row first in the manifest, rows created for
  SystemPreferencesDomain still clone SystemPreferencesDomain metadata,
  and a pre-existing FeatureFlags/ row is preserved byte-for-byte.

Delivery honesty (step8 audit): the Domain file is predicted to be
skipped silently by the restore channel — these tests pin the payload,
never a landing claim.

Run: python tools/test_lg_squair_protocol.py
"""
import hashlib
import os
import plistlib
import sqlite3
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_STORE_TMP = tempfile.mkdtemp(prefix="lgd_squair_test_store_")
os.environ["LGD_STORE_DIR"] = _STORE_TMP


def _install_pyside_stubs():
    class Dummy:
        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, *args, **kwargs):
            return Dummy()

        @staticmethod
        def tr(text, *args, **kwargs):
            return text

        @staticmethod
        def translate(_ctx, text, *args, **kwargs):
            return text

    def make_module(name):
        mod = types.ModuleType(name)

        def __getattr__(attr):
            if attr == "QT_TRANSLATE_NOOP":
                return lambda _ctx, text: text
            cls = type(attr, (Dummy,), {})
            setattr(mod, attr, cls)
            return cls

        mod.__getattr__ = __getattr__
        return mod

    for name in ("PySide6", "PySide6.QtCore", "PySide6.QtGui",
                 "PySide6.QtWidgets"):
        sys.modules[name] = make_module(name)
    sys.modules["PySide6"].QtCore = sys.modules["PySide6.QtCore"]
    sys.modules["PySide6"].QtGui = sys.modules["PySide6.QtGui"]
    sys.modules["PySide6"].QtWidgets = sys.modules["PySide6.QtWidgets"]


try:
    from PySide6 import QtWidgets  # noqa: F401
except Exception:
    _install_pyside_stubs()

from src.tweaks import lg_disable, lg_squair, tweak_loader
from src.tweaks.basic_plist_locations import FileLocation
from src.tweaks.capabilities import tweak_deliverability
from src.tweaks.registry import SPECS_BY_ID, SPECS_BY_SECTION, Section
from src.tweaks.tweaks import tweaks, TweakID

PASS = 0

BASE = {
    "AppleLanguages": ["en-US", "id-ID"],
    "AppleLocale": "en_US",
    "NSForceRightToLeftWritingDirection": False,
    "AKLastIDMSEnvironment": 0,
    "com.apple.finder.WindowState": {"Frame": "{{0, 0}, {320, 240}}"},
}


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def test_registry_shape():
    print("\nregistry shape")
    spec = SPECS_BY_ID[TweakID.LGDisableSquairTest]
    check("Squair spec lives in the LGD section",
          spec.section is Section.LIQUID_GLASS_DISABLE)
    check("section holds the Squair test + Liquid Glass (Latest)",
          [s.id for s in SPECS_BY_SECTION[Section.LIQUID_GLASS_DISABLE]]
          == [TweakID.LGDisableSquairTest, TweakID.LGDisableLatest],
          str([s.id.name
               for s in SPECS_BY_SECTION[Section.LIQUID_GLASS_DISABLE]]))
    check("spec mirrors the HomeDomain GP file",
          spec.location is FileLocation.globalPreferencesHomeDomain)
    check("declared value is a real bool True", spec.value is True
          and type(spec.value) is bool)
    check("gated to iOS 26+", spec.min_version == "26.0")
    check("description carries the honest unproven grade",
          "unproven" in (spec.description or "").lower())
    tweak_loader.load_plist_tweaks()
    tweak = tweaks[TweakID.LGDisableSquairTest]
    check("factory built the Squair tweak class",
          isinstance(tweak, lg_squair.LGDSquairTweak))
    ok, code, _msg = tweak_deliverability(
        TweakID.LGDisableSquairTest, device_version="26.6.1",
        device_build="23G82", is_iphone=True, tweak=tweak)
    check("deliverable on 26.6.1/23G82", ok and code == "OK", code)
    ok, code, _msg = tweak_deliverability(
        TweakID.LGDisableSquairTest, device_version="25.0",
        device_build="", is_iphone=True, tweak=tweak)
    check("locked below iOS 26", not ok and code == "VERSION_BELOW_MIN",
          code)
    check("removed Beta 1 G1/G2 have no spec",
          TweakID.LGDisableG2 not in SPECS_BY_ID
          and TweakID.LGDisableG1 not in SPECS_BY_ID)
    from src.tweaks.capabilities import is_removed_tweak
    check("G1/G2 IDs are recorded as removed tombstones",
          is_removed_tweak(TweakID.LGDisableG2)
          and is_removed_tweak(TweakID.LGDisableG1))


def test_domain_file_bytes():
    print("\nFile Domain payload bytes")
    data = lg_squair.build_domain_file_bytes()
    check("payload is an XML plist", data.startswith(b"<?xml"))
    parsed = plistlib.loads(data)
    check("root dict is exactly the Squair Domain dict",
          parsed == {"SpringBoard":
                     {"SolariumElasticHUD": {"Enabled": False}}})
    enabled = parsed["SpringBoard"]["SolariumElasticHUD"]["Enabled"]
    check("Enabled is a real bool false (not int 0)",
          enabled is False and type(enabled) is bool)
    check("no DevelopmentPhase anywhere in the payload",
          "DevelopmentPhase" not in data.decode("utf-8"))
    check("blob round-trips through the strict loader",
          lg_squair.load_domain_file_dict(data) == parsed)
    check("serialisation is deterministic (sort_keys)",
          data == lg_squair.build_domain_file_bytes())
    try:
        lg_squair.load_domain_file_dict(
            plistlib.dumps({"Other": {}}, fmt=plistlib.FMT_XML))
        raised = False
    except ValueError:
        raised = True
    check("strict loader rejects any other dict", raised)


def test_apply_planner():
    print("\napply planner (File A merge + File Domain)")
    payloads = lg_squair.plan_squair_apply_payloads(dict(BASE))
    check("exactly two inject tuples planned", len(payloads) == 2)
    by_rel = {p[1]: p for p in payloads}
    fa = by_rel[lg_squair.G1_REL_PATH]
    fd = by_rel[lg_squair.DOMAIN_REL_PATH]
    check("File A targets the G1 HomeDomain file",
          fa[0] == "HomeDomain"
          and fa[1] == "Library/Preferences/.GlobalPreferences.plist")
    check("File Domain targets SystemPreferencesDomain",
          fd[0] == "SystemPreferencesDomain")
    check("tuple metadata forced (0644 / 501 / 501) on both payloads",
          all(p[3] == 0o100644 and p[4] == 501 and p[5] == 501
              for p in payloads))
    merged = plistlib.loads(fa[2])
    check("File A keeps every original device key",
          all(merged[k] == BASE[k] for k in BASE))
    check("File A adds exactly the two Squair keys as real bool true",
          merged["SBDisallowGlassTime"] is True
          and merged["SBDisallowGlassButtons"] is True
          and type(merged["SBDisallowGlassTime"]) is bool
          and type(merged["SBDisallowGlassButtons"]) is bool
          and set(merged) == set(BASE) | set(lg_squair.GP_KEYS))
    check("File A never writes the Beta 1 candidate key",
          lg_disable.GP_KEY not in merged)
    check("diff gate is clean for the planned merge",
          lg_disable.diff_gate(BASE, merged,
                               allowed_new=set(lg_squair.GP_KEYS)) == [])
    check("File Domain tuple parses to the exact dict",
          plistlib.loads(fd[2]) == lg_squair.DOMAIN_FILE_DICT)

    both = lg_squair.plan_squair_apply_payloads(
        dict(BASE),
        extra_inserts={lg_disable.GP_KEY: lg_disable.GP_KEY_VALUE})
    merged_both = plistlib.loads(by_rel_key(both, lg_squair.G1_REL_PATH)[2])
    check("G1+G2-style co-apply keeps the candidate key (extra_inserts)",
          merged_both.get(lg_disable.GP_KEY) is True
          and merged_both["SBDisallowGlassTime"] is True)

    try:
        lg_squair.plan_squair_apply_payloads(None)
        raised = False
    except Exception:
        raised = True
    check("planner refuses to plan without a device base", raised)


def by_rel_key(payloads, rel):
    return {p[1]: p for p in payloads}[rel]


def test_rollback_planner():
    print("\nrollback planner (fresh capture minus exactly two keys)")
    fresh = dict(BASE)
    fresh["SBDisallowGlassTime"] = True
    fresh["SBDisallowGlassButtons"] = True
    fresh["NewerDeviceKey"] = "keep"
    payloads, note = lg_squair.plan_squair_rollback_payloads(fresh)
    check("rollback plans exactly one tuple (File A only)",
          len(payloads) == 1 and payloads[0][0] == "HomeDomain"
          and payloads[0][1] == lg_squair.G1_REL_PATH)
    check("no Domain-file tuple in the rollback plan",
          all(p[1] != lg_squair.DOMAIN_REL_PATH for p in payloads))
    rolled = plistlib.loads(payloads[0][2])
    expected = {k: v for k, v in fresh.items() if k not in lg_squair.GP_KEYS}
    check("exactly the two Squair keys removed, everything else intact",
          rolled == expected and "NewerDeviceKey" in rolled)
    check("rollback tuple metadata forced (0644 / 501 / 501)",
          payloads[0][3] == 0o100644 and payloads[0][4] == 501
          and payloads[0][5] == 501)
    check("note states the Domain file cannot be removed by restore",
          "cannot be removed by a restore" in note)
    try:
        lg_squair.plan_squair_rollback_payloads(None)
        raised = False
    except Exception:
        raised = True
    check("rollback planner refuses a missing fresh capture", raised)


def test_tweak_staging_contract():
    print("\ntweak staging contract (never the sparse pass)")
    tweak = tweaks[TweakID.LGDisableSquairTest]
    tweak.set_enabled(True)
    tweak._lgd_base = None
    staged = tweak.apply_tweak({})
    check("unarmed (no device base) stages nothing and is not staged",
          staged == {} and tweak.staged is False)
    tweak._lgd_base = dict(BASE)
    staged = tweak.apply_tweak({})
    check("armed tweak marks staged without touching the sparse dict",
          staged == {} and tweak.staged is True)
    tweak._lgd_base = None
    tweak.set_enabled(False)
    staged = tweak.apply_tweak({})
    check("disabled tweak is never staged",
          staged == {} and tweak.staged is False)


# --- directory-donor behaviour (inject._ensure_directory_rows) --------

def _dir_blob(rel, mode, user, group, inode):
    """An MBFile-style directory blob with marker metadata."""
    return plistlib.dumps({
        "$version": 100000,
        "$archiver": "NSKeyedArchiver",
        "$top": {"root": plistlib.UID(1)},
        "$objects": [
            "$null",
            {
                "Birth": 1, "LastModified": 1, "LastStatusChange": 1,
                "Flags": 0, "GroupID": group, "UserID": user,
                "Mode": mode, "ProtectionClass": 4, "Size": 0,
                "RelativePath": plistlib.UID(2),
                "InodeNumber": inode,
                "$class": plistlib.UID(3),
            },
            rel,
            {"$classname": "MBFile", "$classes": ["MBFile", "NSObject"]},
        ],
    }, fmt=plistlib.FMT_BINARY)


def _manifest_conn(tmp):
    db = os.path.join(tmp, "Manifest.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE Files (fileID TEXT PRIMARY KEY, domain TEXT, "
        "relativePath TEXT, flags INTEGER, file BLOB)")
    # HomeDomain donor FIRST in the table (old code cloned this row for
    # every domain), SystemPreferencesDomain donor second.
    conn.execute(
        "INSERT INTO Files VALUES (?, ?, ?, 2, ?)",
        ("dirhome", "HomeDomain", "Library",
         sqlite3.Binary(_dir_blob("Library", 0o40777, 501, 501, 42))))
    conn.execute(
        "INSERT INTO Files VALUES (?, ?, ?, 2, ?)",
        ("dirsysprefs", "SystemPreferencesDomain", "",
         sqlite3.Binary(_dir_blob("", 0o40755, 0, 0, 43))))
    conn.commit()
    return conn, db


def _row(conn, domain, rel):
    row = conn.execute(
        "SELECT file, flags FROM Files WHERE domain = ? "
        "AND relativePath = ?", (domain, rel)).fetchone()
    if row is None:
        return None, None
    return plistlib.loads(row[0])["$objects"][1], row[1]


def test_directory_donor_same_domain():
    print("\ndirectory rows: same-domain donor wins")
    from src.restore.inject import _ensure_directory_rows
    with tempfile.TemporaryDirectory() as tmp:
        conn, _db = _manifest_conn(tmp)
        _ensure_directory_rows(
            conn, "SystemPreferencesDomain", "FeatureFlags/Domain",
            next_inode=100, known_dirs=set(), donor_blob=None)
        conn.commit()
        ff, ff_flags = _row(conn, "SystemPreferencesDomain", "FeatureFlags")
        ffd, ffd_flags = _row(
            conn, "SystemPreferencesDomain", "FeatureFlags/Domain")
        check("FeatureFlags/ + FeatureFlags/Domain/ rows created (flags=2)",
              ff is not None and ffd is not None
              and ff_flags == 2 and ffd_flags == 2)
        check("new rows clone the SystemPreferencesDomain donor "
              "(mode 040755, root-owned)",
              ff["Mode"] == 0o40755 and ff["UserID"] == 0
              and ff["GroupID"] == 0
              and ffd["Mode"] == 0o40755 and ffd["UserID"] == 0)
        inodes = {ff["InodeNumber"], ffd["InodeNumber"]}
        check("new rows get fresh unique inodes",
              len(inodes) == 2 and min(inodes) > 100)
        conn.close()

    # A pre-existing FeatureFlags/ row must be preserved byte-for-byte.
    with tempfile.TemporaryDirectory() as tmp:
        conn = sqlite3.connect(os.path.join(tmp, "Manifest.db"))
        conn.execute(
            "CREATE TABLE Files (fileID TEXT PRIMARY KEY, domain TEXT, "
            "relativePath TEXT, flags INTEGER, file BLOB)")
        marker = _dir_blob("FeatureFlags", 0o40700, 0, 0, 99)
        fid = hashlib.sha1(
            b"SystemPreferencesDomain-FeatureFlags").hexdigest()
        conn.execute(
            "INSERT INTO Files VALUES (?, ?, ?, 2, ?)",
            (fid, "SystemPreferencesDomain", "FeatureFlags",
             sqlite3.Binary(marker)))
        conn.execute(
            "INSERT INTO Files VALUES (?, ?, ?, 2, ?)",
            ("dirsysprefs", "SystemPreferencesDomain", "",
             sqlite3.Binary(_dir_blob("", 0o40755, 0, 0, 43))))
        conn.commit()
        _ensure_directory_rows(
            conn, "SystemPreferencesDomain", "FeatureFlags/Domain",
            next_inode=100, known_dirs=set(), donor_blob=None)
        conn.commit()
        row = conn.execute(
            "SELECT file FROM Files WHERE domain = ? AND relativePath = ?",
            ("SystemPreferencesDomain", "FeatureFlags")).fetchone()
        check("existing FeatureFlags/ row preserved byte-for-byte",
              bytes(row[0]) == marker)
        ffd, _ = _row(conn, "SystemPreferencesDomain", "FeatureFlags/Domain")
        check("missing child row still created next to a preserved row",
              ffd is not None)
        conn.close()


def main():
    test_registry_shape()
    test_domain_file_bytes()
    test_apply_planner()
    test_rollback_planner()
    test_tweak_staging_contract()
    test_directory_donor_same_domain()
    print(f"\n{PASS} checks passed")


if __name__ == "__main__":
    main()
