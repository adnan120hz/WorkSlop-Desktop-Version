#!/usr/bin/env python3
"""Offline tests for the Wave 10 Apply Journal (buildspec R6 §3).

Unit level: schema, atomic write (no .tmp left), retention, value
redaction, file records from FileToRestore-shaped objects.

Integration level (needs PySide6 + pymobiledevice3 + cffi; skipped
cleanly without them): a real DeviceManager tweak pass against a stubbed
restore, proving exactly one entry per enabled tweak with the right
status/skip_reason, delivered vs not-delivered transitions, the failed
restore leaving no new lastapply record, and a reset journal.

Run: python tools/test_apply_journal.py
"""
import glob
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PASS = 0
TMP = tempfile.mkdtemp(prefix="worksj-")
os.environ["WORKSLOP_APPLY_JOURNAL_DIR"] = os.path.join(TMP, "journal")


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


from src.controllers import apply_journal as aj  # noqa: E402


def test_value_summary():
    print("\nvalue_summary redaction")
    check("bool as-is", aj.value_summary(True) is True)
    check("int as-is", aj.value_summary(7) == 7)
    check("short str as-is", aj.value_summary("hello") == "hello")
    long_str = "x" * 200
    s = aj.value_summary(long_str)
    check("long str summarized", isinstance(s, dict) and s["type"] == "str"
          and s["length"] == 200 and len(s["sha256"]) == 64)
    check("long str not present", long_str not in json.dumps(s))
    s = aj.value_summary("user typed this", sensitive=True)
    check("sensitive str always summarized",
          isinstance(s, dict) and "user typed" not in json.dumps(s))
    s = aj.value_summary({"b": 1, "a": [1, 2]})
    check("dict keys only", s["keys"] == ["a", "b"]
          and s["type"] == "dict")
    s = aj.value_summary(b"\x00\x01")
    check("bytes summarized", s["type"] == "bytes" and s["length"] == 2)


def test_journal_document():
    print("\njournal document lifecycle")
    jdir = os.path.join(TMP, "doc")
    journal = aj.begin_journal(
        "apply", device={"name": "iPhone", "model": "iPhone14,5",
                         "ios": "26.6.1", "build": "23G83", "udid": "U1"},
        journal_dir=jdir)
    entry = journal.add_entry({"id": "x", "tweak_id": "X", "name": "X"})
    check("begin written", os.path.exists(journal.path))
    check("default status requested", entry["status"] == "requested")

    class FakeFile:
        domain = "HomeDomain"
        restore_path = "/Library/SpringBoard/statusBarOverrides"
        contents = b"\x01" * 3944
        owner = 501
        group = 501

    keys = journal.attach_files([FakeFile()])
    check("file key shape",
          keys == ["HomeDomain/Library/SpringBoard/statusBarOverrides"])
    journal.associate(entry, keys)
    journal._prune  # noqa: B018 - attribute exists
    journal.finalize("success")
    check("no tmp left", not os.path.exists(journal.path + ".tmp"))
    with open(journal.path) as fh:
        doc = json.load(fh)
    check("schema version", doc["schema_version"] == 1)
    check("mode apply", doc["mode"] == "apply")
    check("app recorded", doc["app"]["version"] and "build" in doc["app"])
    check("device recorded", doc["device"]["build"] == "23G83"
          and doc["device"]["ios"] == "26.6.1")
    check("timestamps + duration",
          doc["started_at"].endswith("Z") and doc["ended_at"].endswith("Z")
          and isinstance(doc["duration_ms"], int))
    f0 = doc["files"][0]
    check("file record fields", f0["domain"] == "HomeDomain"
          and f0["size"] == 3944 and len(f0["sha1"]) == 40
          and f0["owner"] == 501)
    check("entry references file",
          doc["tweaks"][0]["files"] == keys)
    check("no password-like keys anywhere",
          "password" not in json.dumps(doc).lower())


def test_file_records_from_disk_and_errors():
    print("\nfile records: contents_path + unreadable")
    path = os.path.join(TMP, "payload.bin")
    with open(path, "wb") as fh:
        fh.write(b"abc")

    class PathFile:
        domain = "ManagedPreferencesDomain"
        restore_path = "mobile/x.plist"
        contents = None
        contents_path = path
        owner = 501
        group = 501

    rec = aj.build_file_record(PathFile())
    check("contents_path hashed", rec["size"] == 3 and len(rec["sha1"]) == 40)

    class MissingFile(PathFile):
        contents_path = os.path.join(TMP, "does-not-exist.bin")

    rec = aj.build_file_record(MissingFile())
    check("unreadable -> nulls + error, no raise",
          rec["size"] is None and rec["sha1"] is None and "error" in rec)


def test_retention():
    print("\nretention keeps newest 100 per prefix")
    jdir = os.path.join(TMP, "retain")
    os.makedirs(jdir, exist_ok=True)
    for i in range(105):
        p = os.path.join(jdir, f"apply-old{i:03d}.json")
        with open(p, "w") as fh:
            fh.write("{}")
        os.utime(p, (1000000 + i, 1000000 + i))
    journal = aj.begin_journal("apply", journal_dir=jdir)
    journal.finalize("success")
    remaining = glob.glob(os.path.join(jdir, "apply-*.json"))
    check("<=100 apply journals remain", len(remaining) <= 100,
          str(len(remaining)))
    check("newest kept", os.path.exists(journal.path))


def test_manager_integration():
    print("\nDeviceManager integration (apply + reset)")
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        import src.devicemanagement.device_manager as dm_mod
        from src.tweaks.tweaks import tweaks, TweakID
        from src.tweaks.tweak_loader import (
            load_mobilegestalt, load_plist_tweaks)
        from src.utils.pages import Page
    except Exception as e:
        print(f"  skipped: {type(e).__name__}: {e}")
        return
    app = QApplication.instance() or QApplication([])
    jdir = os.environ["WORKSLOP_APPLY_JOURNAL_DIR"]
    os.makedirs(jdir, exist_ok=True)
    load_plist_tweaks()
    # Register MobileGestalt tweaks under a supported build; the apply
    # below runs against 23G83, whose shared decision must lock them.
    load_mobilegestalt(build="23C5027f", version="26.1")

    dm = dm_mod.DeviceManager()
    dm.get_current_device_name = lambda: "Test iPhone"
    dm.get_current_device_model = lambda: "iPhone14,5"
    dm.get_current_device_version = lambda: "26.6.1"
    dm.get_current_device_build = lambda: "23G83"
    dm.get_current_device_udid = lambda: "TESTUDID-JOURNAL"
    dm._raise_if_unsupported = lambda: None

    restored = {"mode": "ok"}

    async def fake_restore(files, update_label=lambda x: None, **kw):
        if restored["mode"] == "raise":
            raise RuntimeError("restore boom")
        restored["files"] = list(files)
        return "OK"
    dm.start_restore = fake_restore

    async def fake_skip_setup(files, restoring_domains):
        return None
    dm.add_skip_setup = fake_skip_setup

    def latest_journal(mode):
        files = sorted(glob.glob(os.path.join(jdir, f"{mode}-*.json")),
                       key=os.path.getmtime)
        with open(files[-1]) as fh:
            return json.load(fh)

    enabled = []
    def enable(tid):
        tweaks[tid].set_enabled(True)
        enabled.append(tid)

    try:
        # Fake tweak set: registry plist (ship-candidate), registry TEXT
        # (HotLoad victim below), research-only, MobileGestalt on a locked
        # build, Status Bar no-SIM feature.
        enable(TweakID.SBHideLowPowerAlerts)
        enable(TweakID.LockScreenFootnote)
        enable(TweakID.SolariumForceFallback)
        enable(TweakID.ModelName)
        sb = tweaks[TweakID.StatusBar]
        sb.set_enabled(True)
        sb.set_full_signal_bars_no_sim()
        enabled.append(TweakID.StatusBar)

        # HotLoad rule against the footnote tweak (cache file the loader
        # reads; rule semantics: disabled=true means the rule is active).
        from src.controllers.hotload import HotLoad, _rules_path
        rules_file = _rules_path()
        with open(rules_file, "w") as fh:
            json.dump({"version": 1, "rules": [
                {"tweak": "LockScreenFootnote", "disabled": True}]}, fh)

        # ---- successful apply (through apply_changes, like ApplyThread)
        dm.apply_changes(lambda x: None, lambda x: None)
        doc = latest_journal("apply")
        by_id = {e["tweak_id"]: e for e in doc["tweaks"]}
        check("journal path surfaced",
              bool(dm.last_apply_journal_path)
              and os.path.exists(dm.last_apply_journal_path))
        check("operation success", doc["status"] == "success")
        check("one entry per enabled tweak",
              set(by_id) == {"SBHideLowPowerAlerts", "LockScreenFootnote",
                             "SolariumForceFallback", "ModelName",
                             "StatusBar"}, str(sorted(by_id)))
        check("registry plist delivered",
              by_id["SBHideLowPowerAlerts"]["status"]
              == "delivered-by-restore")
        plist_entry = by_id["SBHideLowPowerAlerts"]
        check("plist entry has file + key",
              plist_entry["files"] and plist_entry["operation"]["key"]
              == "SBHideLowPowerAlerts")
        check("device fields recorded",
              doc["device"]["ios"] == "26.6.1"
              and doc["device"]["build"] == "23G83")
        check("hotload skip recorded",
              by_id["LockScreenFootnote"]["status"] == "skipped"
              and by_id["LockScreenFootnote"]["skip_reason"]
              == "hotload_rule")
        check("device-test candidate delivered (journal-recorded)",
              by_id["SolariumForceFallback"]["status"] == "delivered-by-restore"
              and by_id["SolariumForceFallback"]["files"],
              str(by_id["SolariumForceFallback"].get("status")))
        check("gestalt locked skip recorded",
              by_id["ModelName"]["status"] == "skipped"
              and by_id["ModelName"]["skip_reason"]
              == "mobilegestalt_unsupported_build")
        sb_entries = [e for e in doc["tweaks"]
                      if e["tweak_id"] == "StatusBar"]
        # Wave 11 (user order 2026-10-03): the Status Bar feature is a
        # normal active tweak — the AUDIT_RESEARCH_ONLY containment is
        # gone, so on the 26.6.1 target it keeps its own journal
        # identity AND delivers like any other special feature.
        check("statusbar feature is its own entry and delivers",
              any(e["id"] == "statusbar.full_signal_bars_no_sim"
                  and e["status"] == "delivered-by-restore"
                  and e["files"]
                  for e in sb_entries), str(sb_entries))
        check("top-level files carry sha1/size",
              all(f["sha1"] and f["size"] is not None
                  for f in doc["files"]))
        check("no password in journal json",
              "password" not in json.dumps(doc).lower())

        from src.restore.lastapply import load_lastapply, sparse_signature
        sig_after_success = load_lastapply("TESTUDID-JOURNAL")

        # ---- failed restore: not-delivered + no new lastapply
        restored["mode"] = "raise"
        try:
            dm.apply_changes(lambda x: None, lambda x: None)
        except Exception:
            pass
        doc2 = latest_journal("apply")
        check("failed restore journal persisted failed",
              doc2["status"] == "failed", doc2["status"])
        by_id2 = {e["tweak_id"]: e for e in doc2["tweaks"]}
        check("staged -> not-delivered on restore failure",
              by_id2["SBHideLowPowerAlerts"]["status"] == "not-delivered")
        check("lastapply untouched by failed apply",
              load_lastapply("TESTUDID-JOURNAL") == sig_after_success)
        restored["mode"] = "ok"

        # ---- reset journal
        dm.reset_tweaks([Page.StatusBar], None, lambda x: None,
                        lambda x: None)
        rdoc = latest_journal("reset")
        check("reset mode recorded", rdoc["mode"] == "reset")
        check("reset one entry delivered",
              len(rdoc["tweaks"]) == 1
              and rdoc["tweaks"][0]["status"] == "delivered-by-restore")
        check("reset stages classic struct",
              any(f["path"].endswith("statusBarOverrides")
                  and f["size"] == 3944 for f in rdoc["files"]),
              str(rdoc["files"]))
    finally:
        for tid in enabled:
            try:
                tweaks[tid].set_enabled(False)
            except Exception:
                pass
        try:
            tweaks[TweakID.StatusBar].unset_full_signal_bars_no_sim()
        except Exception:
            pass


def test_gestalt_journal():
    print("\nMobileGestalt page apply is journal-recorded (debt fix)")
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from contextlib import asynccontextmanager
        from types import SimpleNamespace
        import src.devicemanagement.device_manager as dm_mod
        from src.tweaks.tweaks import tweaks, TweakID
        from src.tweaks.tweak_loader import load_mobilegestalt, load_plist_tweaks
    except Exception as e:
        print(f"  skipped: {type(e).__name__}: {e}")
        return
    app = QApplication.instance() or QApplication([])
    jdir = os.environ["WORKSLOP_APPLY_JOURNAL_DIR"]
    os.makedirs(jdir, exist_ok=True)
    load_plist_tweaks()
    load_mobilegestalt(build="23C5027f", version="26.1")

    dm = dm_mod.DeviceManager()
    dm.get_current_device_name = lambda: "Test iPhone"
    dm.get_current_device_model = lambda: "iPhone14,5"
    dm.get_current_device_version = lambda: "26.1"
    dm.get_current_device_build = lambda: "23C5027f"
    dm.get_current_device_udid = lambda: "TESTUDID-GESTALT"
    dm.data_singleton.current_device = SimpleNamespace(
        connected_via_usb=True, version="26.1", build="23C5027f")
    dm._load_gestalt_plist = lambda update_label=None: {
        "CacheExtra": {"oPeik/9e8lQWMszEjbPzng": {}}}
    dm.pref_manager.auto_reboot = False

    @asynccontextmanager
    async def fake_lockdown(serial=None, **kw):
        yield SimpleNamespace()

    captured = {}

    async def fake_restore_files(**kw):
        captured["files"] = list(kw.get("files") or [])
        if captured.get("fail"):
            raise RuntimeError("gestalt restore boom")
        return "OK"

    old_lockdown = dm_mod.lockdown_session
    old_restore = dm_mod.restore_files
    dm_mod.lockdown_session = fake_lockdown
    dm_mod.restore_files = fake_restore_files

    def latest_apply():
        files = sorted(glob.glob(os.path.join(jdir, "apply-*.json")),
                       key=os.path.getmtime)
        with open(files[-1]) as fh:
            return json.load(fh)

    tweak = tweaks[TweakID.ModelName]
    tweak.set_enabled(True)
    try:
        dm.apply_gestalt_tweaks(lambda x: None, lambda x: None)
        doc = latest_apply()
        check("gestalt apply journal written", doc["mode"] == "apply")
        check("gestalt apply journal success", doc["status"] == "success",
              doc["status"])
        entries = [e for e in doc["tweaks"] if e["tweak_id"] == "ModelName"]
        check("gestalt tweak entry recorded", len(entries) == 1,
              str(doc["tweaks"]))
        check("gestalt entry delivered",
              bool(entries)
              and entries[0]["status"] == "delivered-by-restore",
              str(entries))
        check("gestalt journal path surfaced",
              bool(dm.last_apply_journal_path)
              and os.path.exists(dm.last_apply_journal_path))

        captured["fail"] = True
        raised = False
        try:
            dm.apply_gestalt_tweaks(lambda x: None, lambda x: None)
        except Exception:
            raised = True
        check("failing gestalt apply propagates", raised)
        doc2 = latest_apply()
        check("failed gestalt apply journaled failed",
              doc2["status"] == "failed", doc2["status"])
        entries2 = [e for e in doc2["tweaks"] if e["tweak_id"] == "ModelName"]
        check("failed gestalt entries not delivered",
              bool(entries2)
              and entries2[0]["status"] == "not-delivered",
              str(entries2))
    finally:
        tweak.set_enabled(False)
        dm_mod.lockdown_session = old_lockdown
        dm_mod.restore_files = old_restore


test_value_summary()
test_journal_document()
test_file_records_from_disk_and_errors()
test_retention()
test_manager_integration()
test_gestalt_journal()

print(f"\nALL {PASS} CHECKS PASSED")
