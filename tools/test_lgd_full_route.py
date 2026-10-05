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


def _write_synthetic_backup(backup_root, udid, g1_dict, g2_dict, omit_g1=False):
    device_dir = os.path.join(backup_root, udid)
    os.makedirs(device_dir, exist_ok=True)
    # Keep an older run's injected payload from leaking into this backup.
    db_path = os.path.join(device_dir, "Manifest.db")
    if os.path.exists(db_path):
        os.unlink(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE Files (fileID TEXT PRIMARY KEY, domain TEXT, "
        "relativePath TEXT, flags INTEGER, file BLOB)")

    def add(domain, rel, data):
        fid = hashlib.sha1(f"{domain}-{rel}".encode()).hexdigest()
        payload_dir = os.path.join(device_dir, fid[:2])
        os.makedirs(payload_dir, exist_ok=True)
        with open(os.path.join(payload_dir, fid), "wb") as fh:
            fh.write(data)
        conn.execute(
            "INSERT INTO Files VALUES (?, ?, ?, 1, ?)",
            (fid, domain, rel, sqlite3.Binary(b"x" * 64)))

    for i in range(3):
        add("HomeDomain", f"Library/Preferences/com.apple.dummy{i}.plist",
            plistlib.dumps({"i": i}))
    if not omit_g1 and g1_dict is not None:
        add(lg_disable.G1_DOMAIN, lg_disable.G1_REL_PATH,
            plistlib.dumps(g1_dict))
    if g2_dict is not None:
        add(lg_disable.G2_DOMAIN, lg_disable.G2_REL_PATH,
            plistlib.dumps(g2_dict))
    conn.commit()
    conn.close()


def test_full_route_end_to_end():
    print("\nfull route end-to-end (stubbed device stack)")
    import asyncio
    from contextlib import asynccontextmanager
    from pathlib import Path
    from src.devicemanagement import session as session_mod
    from src.restore import inject as inject_mod
    from src.restore import protective as protective_mod
    from src.restore import restore as restore_mod
    from src.utils import stall_watchdog as watchdog_mod
    from src.exceptions.nugget_exception import NuggetException

    udid2 = "TESTUDIDLGDFULLROUTE00000000000000002"
    base = {"AppleLocale": "en_US", "AppleLanguages": ["en-US"],
            "ExistingKey": 7}
    device_g2 = {"MDMKey": "keepme", "OtherKey": 3}
    cfg = {"encrypted": False, "omit_g1": False}
    calls = {"restore": 0}

    class FakeMB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get_will_encrypt(self):
            return cfg["encrypted"]

        async def backup(self, full, backup_directory, progress_callback=None):
            _write_synthetic_backup(
                backup_directory, udid2, base, device_g2,
                omit_g1=cfg["omit_g1"])

    @asynccontextmanager
    async def fake_session(_udid):
        yield object()

    async def fake_disk(_lc, path=None):
        return 10 ** 12

    async def fake_watch(fn, _progress, operation=None):
        return await fn(lambda _x: None)

    async def fake_restore(_lc, backup_root, _udid, reboot,
                           progress_callback, backup_password=""):
        assert os.path.isfile(
            os.path.join(backup_root, _udid, "Manifest.db"))
        calls["restore"] += 1

    saved_attrs = [
        (session_mod, "lockdown_session", session_mod.lockdown_session),
        (protective_mod, "check_disk_space_for_backup",
         protective_mod.check_disk_space_for_backup),
        (restore_mod, "_restore_protective_backup",
         restore_mod._restore_protective_backup),
        (restore_mod, "_start_mobilebackup2", restore_mod._start_mobilebackup2),
        (watchdog_mod, "run_with_stall_watchdog",
         watchdog_mod.run_with_stall_watchdog),
        (inject_mod, "_is_encrypted_backup", inject_mod._is_encrypted_backup),
        (lgd_full, "lgd_backup_base", lgd_full.lgd_backup_base),
    ]
    pool = tempfile.mkdtemp(prefix="lgd_full_pool_")
    session_mod.lockdown_session = fake_session
    protective_mod.check_disk_space_for_backup = fake_disk
    restore_mod._restore_protective_backup = fake_restore
    restore_mod._start_mobilebackup2 = lambda _lc: FakeMB()
    watchdog_mod.run_with_stall_watchdog = fake_watch
    lgd_full.lgd_backup_base = lambda _u: Path(pool)
    try:
        # A) Apply G1+G2: reaches the restore (this is the path that died
        #    with UnboundLocalError before the audit fix), G2 is rebased
        #    onto the device's own managed file.
        payloads = lgd_full.plan_apply_payloads(
            g1_active=True, g2_active=True, g1_base=base)
        root = asyncio.run(lgd_full.run_full_backup_route(
            udid2, payloads, g1_base=base,
            version="26.6.1", build="23G83"))
        check("apply route completes and restores", calls["restore"] == 1)
        g2_disk = plistlib.loads(open(lgd_full.payload_disk_path(
            root, udid2, lg_disable.G2_DOMAIN, lg_disable.G2_REL_PATH),
            "rb").read())
        check("G2 rebased: pre-existing managed keys survive",
              g2_disk.get("MDMKey") == "keepme"
              and g2_disk.get("OtherKey") == 3, str(g2_disk))
        check("G2 rebased: candidate key present as bool true",
              g2_disk.get(KEY) is True)
        check("G1 original saved for rollback",
              lg_disable.original_saved(udid2))
        saved_g2 = lg_disable.load_g2_original(udid2)
        check("G2 original captured from the apply backup",
              saved_g2 is not None
              and plistlib.loads(saved_g2).get("MDMKey") == "keepme")

        # B) Rollback G2 via the same route restores the saved original.
        rb = lgd_full.plan_rollback_payloads(
            "g2", None, g2_original_bytes=saved_g2)
        root_b = asyncio.run(lgd_full.run_full_backup_route(
            udid2, rb, apply_mode=False, expect_candidate_key=False))
        g2_disk = plistlib.loads(open(lgd_full.payload_disk_path(
            root_b, udid2, lg_disable.G2_DOMAIN, lg_disable.G2_REL_PATH),
            "rb").read())
        check("G2 rollback restores pre-tweak overlay, key gone",
              g2_disk.get("MDMKey") == "keepme" and KEY not in g2_disk,
              str(g2_disk))
        check("rollback did not poison the saved G2 original",
              plistlib.loads(lg_disable.load_g2_original(udid2)).get(
                  "MDMKey") == "keepme")

        # C) Encrypted backup: refused honestly, restore never called.
        cfg["encrypted"] = True
        calls["restore"] = 0
        try:
            asyncio.run(lgd_full.run_full_backup_route(
                udid2, lgd_full.plan_apply_payloads(
                    g1_active=False, g2_active=True, g1_base=None)))
            raised = None
        except NuggetException as exc:
            raised = exc
        check("encrypted backup refused with friendly error",
              raised is not None and "encrypted" in str(raised).lower())
        check("encrypted refusal happens before any restore",
              calls["restore"] == 0)
        cfg["encrypted"] = False

        # D) G1 with no base anywhere: friendly NuggetException, NOT an
        #    UnboundLocalError, and no restore.
        cfg["omit_g1"] = True
        try:
            asyncio.run(lgd_full.run_full_backup_route(
                udid2, lgd_full.plan_apply_payloads(
                    g1_active=True, g2_active=False, g1_base=base),
                g1_base=None))
            raised = None
        except NuggetException as exc:
            raised = exc
        except Exception as exc:  # noqa: BLE001 - the regression itself
            raised = exc
        check("G1 without a readable device file fails friendly",
              isinstance(raised, NuggetException), repr(raised))
        cfg["omit_g1"] = False

        # E) Pool pruning keeps only the newest completed LGD runs.
        pool_e = tempfile.mkdtemp(prefix="lgd_full_pool_e_")
        lgd_full.lgd_backup_base = lambda _u: Path(pool_e)
        for i in range(4):
            run_dir = os.path.join(pool_e, f"run{i}")
            _write_synthetic_backup(
                os.path.join(run_dir, "device_backup"), udid2, base, None)
            os.utime(run_dir, (1000 + i, 1000 + i))
        incomplete = os.path.join(pool_e, "run-incomplete")
        os.makedirs(os.path.join(incomplete, "device_backup"), exist_ok=True)
        removed = lgd_full.prune_lgd_backups(udid2, keep=2)
        remaining = sorted(os.listdir(pool_e))
        check("LGD pool pruning bounds disk usage",
              removed == 2 and "run2" in remaining and "run3" in remaining,
              str(remaining))
        check("incomplete runs are never pruned",
              "run-incomplete" in remaining)
    finally:
        for module, attr, value in saved_attrs:
            setattr(module, attr, value)


def main():
    test_gate()
    test_plan_payloads()
    test_staged_split()
    test_inject_and_verify()
    test_full_route_end_to_end()
    test_merge_duplicates_hardened()
    print(f"\nALL {PASS} CHECKS PASSED")




def test_merge_duplicates_hardened():
    print("\nmerge_duplicates empty/unparseable tolerance (sparse path)")
    from src.restore.restore import merge_duplicates
    from src.utils.file_to_restore import FileToRestore

    def rec(contents, path="Library/Preferences/.GlobalPreferences.plist"):
        return FileToRestore(contents=contents, restore_path=path,
                             domain="HomeDomain")

    good = plistlib.dumps({"a": 1})
    merged = merge_duplicates([rec(b""), rec(good)])
    check("empty first record takes the valid duplicate",
          len(merged) == 1 and plistlib.loads(merged[0].contents) == {"a": 1})
    merged = merge_duplicates([rec(good), rec(b"")])
    check("empty duplicate contributes nothing",
          len(merged) == 1 and plistlib.loads(merged[0].contents) == {"a": 1})
    merged = merge_duplicates([rec(good), rec(b"not a plist")])
    check("unparseable duplicate is ignored, restore survives",
          len(merged) == 1 and plistlib.loads(merged[0].contents) == {"a": 1})
    merged = merge_duplicates([rec(good), rec(plistlib.dumps({"b": 2}))])
    check("two valid duplicates still merge",
          plistlib.loads(merged[0].contents) == {"a": 1, "b": 2})


if __name__ == "__main__":
    main()
