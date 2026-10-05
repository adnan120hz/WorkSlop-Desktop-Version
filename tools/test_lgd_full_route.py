#!/usr/bin/env python3
"""Offline tests for the Liquid Glass Disable full-backup route (iOS 26.6.x).

Pins the contract of src/restore/lgd_full.py without any device:

* the route applies ONLY on iOS 26.6.x builds 23G82/23G83;
* payload planning refuses G1 without the device's own file as base;
* staged apply records are split out of the sparse pass with their
  gate-approved content intact;
* injection into a synthetic backup + on-disk re-verification passes
  for honest payloads and fails for tampered / wrong-type / key-losing
  ones;
* rollback payload planning (empty G2 overlay, saved G1 original).

Run: python tools/test_lgd_full_route.py
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
_STORE_TMP = tempfile.mkdtemp(prefix="lgd_full_test_store_")
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

from src.tweaks import lg_disable
from src.restore import lgd_full
from src.restore.inject import inject_files_into_backup
from src.utils.file_to_restore import FileToRestore

PASS = 0
KEY = lg_disable.GP_KEY
UDID = "TESTUDID0000000000000000000000000001"


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def _record(domain, rel_path, contents):
    return FileToRestore(contents=contents, restore_path=rel_path,
                         domain=domain, owner=501, group=501)


def test_gate():
    print("\nroute gate (exact window only)")
    check("26.6.1 / 23G83 (final) applies",
          lgd_full.lgd_full_route_applicable("26.6.1", "23G83"))
    check("26.6.1 / 23G82 (RC) applies",
          lgd_full.lgd_full_route_applicable("26.6.1", "23G82"))
    check("26.6.0 / 23G83 applies",
          lgd_full.lgd_full_route_applicable("26.6", "23G83"))
    check("26.5.2 rejected",
          not lgd_full.lgd_full_route_applicable("26.5.2", "23G83"))
    check("26.7 rejected",
          not lgd_full.lgd_full_route_applicable("26.7", "23G83"))
    check("27.0 rejected (has its own flow)",
          not lgd_full.lgd_full_route_applicable("27.0", "24A100"))
    check("unknown build rejected",
          not lgd_full.lgd_full_route_applicable("26.6.1", "23G80"))
    check("empty version/build rejected",
          not lgd_full.lgd_full_route_applicable("", "")
          and not lgd_full.lgd_full_route_applicable(None, None))


def test_plan_payloads():
    print("\npayload planning")
    base = {"AppleLocale": "en_US", "AppleLanguages": ["en-US"]}
    payloads = lgd_full.plan_apply_payloads(
        g1_active=True, g2_active=True, g1_base=base)
    check("both routes planned", len(payloads) == 2)
    by_domain = {p[0]: p for p in payloads}
    g2 = plistlib.loads(by_domain[lg_disable.G2_DOMAIN][2])
    check("G2 payload carries the key as real bool true",
          g2.get(KEY) is True and type(g2.get(KEY)) is bool)
    g1 = plistlib.loads(by_domain[lg_disable.G1_DOMAIN][2])
    check("G1 payload keeps every original key and adds the key",
          g1.get("AppleLocale") == "en_US" and g1.get(KEY) is True)
    try:
        lgd_full.plan_apply_payloads(
            g1_active=True, g2_active=False, g1_base=None)
        raised = False
    except Exception:
        raised = True
    check("G1 without a device base refuses to plan", raised)
    g2_only = lgd_full.plan_apply_payloads(
        g1_active=False, g2_active=True, g1_base=None)
    check("G2 alone plans without a base", len(g2_only) == 1)


def test_staged_split():
    print("\nstaged record split")
    base = {"AppleLocale": "en_US"}
    g1_bytes = lg_disable.build_g1_payload(base, {KEY: True})
    g2_bytes = lg_disable.build_g2_payload({KEY: True})
    other = _record("HomeDomain", "Library/Preferences/com.apple.test.plist",
                    plistlib.dumps({"x": 1}))
    files = [
        _record(lg_disable.G2_DOMAIN, lg_disable.G2_REL_PATH, g2_bytes),
        _record(lg_disable.G1_DOMAIN, lg_disable.G1_REL_PATH, g1_bytes),
        other,
    ]
    remaining, payloads = lgd_full.payloads_from_staged_files(
        files, g1_active=True, g2_active=True)
    check("LGD records leave the sparse list", remaining == [other])
    check("two payloads diverted", len(payloads) == 2)
    parsed = {p[0]: plistlib.loads(p[2]) for p in payloads}
    check("diverted G1 content is the gate-approved merge",
          parsed[lg_disable.G1_DOMAIN].get("AppleLocale") == "en_US"
          and parsed[lg_disable.G1_DOMAIN].get(KEY) is True)
    remaining2, payloads2 = lgd_full.payloads_from_staged_files(
        files, g1_active=False, g2_active=False)
    check("inactive routes divert nothing",
          remaining2 == files and payloads2 == [])


def _make_backup(root):
    device_dir = os.path.join(root, UDID)
    os.makedirs(device_dir, exist_ok=True)
    db = os.path.join(device_dir, "Manifest.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE Files (fileID TEXT PRIMARY KEY, domain TEXT, "
        "relativePath TEXT, flags INTEGER, file BLOB)")
    # A couple of real rows so the manifest looks like a device backup
    # (and clears the injector's minimum-size sanity check).
    for i in range(4):
        rel = f"Library/Preferences/com.apple.dummy{i}.plist"
        data = plistlib.dumps({"i": i})
        fid = hashlib.sha1(f"HomeDomain-{rel}".encode()).hexdigest()
        payload_dir = os.path.join(device_dir, fid[:2])
        os.makedirs(payload_dir, exist_ok=True)
        with open(os.path.join(payload_dir, fid), "wb") as fh:
            fh.write(data)
        conn.execute(
            "INSERT INTO Files VALUES (?, ?, ?, 1, ?)",
            (fid, "HomeDomain", rel, sqlite3.Binary(b"x" * 64)))
    conn.commit()
    conn.close()
    return root


def test_inject_and_verify():
    print("\ninjection + hard verification (synthetic backup)")
    with tempfile.TemporaryDirectory() as tmp:
        root = _make_backup(os.path.join(tmp, "backup"))
        base = {"AppleLocale": "en_US", "AppleLanguages": ["en-US"]}
        payloads = lgd_full.plan_apply_payloads(
            g1_active=True, g2_active=True, g1_base=base)
        injected, unchanged, failed = inject_files_into_backup(
            root, UDID, payloads)
        check("injection accounts for every file",
              failed == 0 and injected + unchanged == len(payloads),
              f"{injected}/{unchanged}/{failed}")
        problems = lgd_full.verify_injected_payloads(
            root, UDID, payloads, g1_base=base)
        check("honest injected backup verifies clean", problems == [],
              str(problems))

        # Tamper: flip the G2 payload bytes on disk.
        g2_path = lgd_full.payload_disk_path(
            root, UDID, lg_disable.G2_DOMAIN, lg_disable.G2_REL_PATH)
        with open(g2_path, "wb") as fh:
            fh.write(plistlib.dumps({KEY: "true"}, fmt=plistlib.FMT_BINARY))
        problems = lgd_full.verify_injected_payloads(
            root, UDID, payloads, g1_base=base)
        check("tampered / wrong-type payload is caught", len(problems) > 0,
              str(problems))

        # Key-losing G1 payload must fail the diff gate.
        bad_g1 = [(lg_disable.G1_DOMAIN, lg_disable.G1_REL_PATH,
                   plistlib.dumps({KEY: True}), 0o100644, 501, 501)]
        inject_files_into_backup(root, UDID, bad_g1)
        problems = lgd_full.verify_injected_payloads(
            root, UDID, bad_g1, g1_base=base)
        check("key-losing G1 payload fails the diff gate",
              any("LOST" in p for p in problems), str(problems))

        # Rollback payloads verify without the candidate key.
        rb = lgd_full.plan_rollback_payloads(
            "g1", lg_disable.build_g1_payload(base, {}))
        inject_files_into_backup(root, UDID, rb)
        problems = lgd_full.verify_injected_payloads(
            root, UDID, rb, g1_base=base, expect_candidate_key=False)
        check("rollback payloads verify clean", problems == [],
              str(problems))
        try:
            lgd_full.plan_rollback_payloads("g1", None)
            raised = False
        except Exception:
            raised = True
        check("G1 rollback without a saved original refuses", raised)


def main():
    test_gate()
    test_plan_payloads()
    test_staged_split()
    test_inject_and_verify()
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
