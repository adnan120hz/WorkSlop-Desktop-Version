#!/usr/bin/env python3
"""Fix Audit 5: Apply Journal coverage for PosterBoard / Templates /
Passcode / Gestalt.

The journal snapshot used to live inside the tweak pass and only looked
at ``enabled`` — PosterBoard and Templates are content-driven (their
``enabled`` flag is never set), so they were never journaled; the
Passcode page wrote to the device with no journal at all; and an abort
before the tweak pass left a journal with zero tweaks.

Proofs here (offscreen, stubbed restore / AirLift):
* a main Apply with queued PosterBoard + Templates content and an
  enabled (locked) Gestalt tweak records entries for ALL of them;
* the entries are already ON DISK, staged, at the moment the restore
  starts (i.e. recorded before apply runs, not after);
* a Passcode theme write opens a journal before ``write_files`` is
  called and finalizes it delivered / failed honestly.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit5_apply_journal_coverage.py
"""
import glob
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0
TMP = tempfile.mkdtemp(prefix="works-audit5-")
os.environ["WORKSLOP_APPLY_JOURNAL_DIR"] = os.path.join(TMP, "journal")


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def latest_journal(mode="apply"):
    files = sorted(glob.glob(os.path.join(
        os.environ["WORKSLOP_APPLY_JOURNAL_DIR"], f"{mode}-*.json")),
        key=os.path.getmtime)
    with open(files[-1]) as fh:
        return json.load(fh)


class FakeTendie:
    name = "fake.tendie"
    descriptor_cnt = 0
    unsafe_container = False

    def extract(self, output_dir=None):
        contents = os.path.join(output_dir, "descriptor", "versions", "0",
                                "contents")
        os.makedirs(contents, exist_ok=True)
        with open(os.path.join(contents, "fake.txt"), "wb") as fh:
            fh.write(b"posterboard-descriptor")


class FakeTemplate:
    name = "fake.batter"
    domain = "AppDomain-com.apple.TestTemplate"
    change_bundle_id = False
    bundle_id = "com.apple.TestTemplate"

    def extract(self, output_dir=None):
        container = os.path.join(output_dir, "container")
        os.makedirs(container, exist_ok=True)
        with open(os.path.join(container, "template.txt"), "wb") as fh:
            fh.write(b"template-payload")


def test_main_apply_coverage():
    print("\nmain Apply: PosterBoard/Templates/Gestalt journaled pre-restore")
    from PySide6.QtWidgets import QApplication
    import src.devicemanagement.device_manager as dm_mod
    from src.tweaks.tweaks import tweaks, TweakID
    from src.tweaks.tweak_loader import load_mobilegestalt, load_plist_tweaks

    app = QApplication.instance() or QApplication([])
    jdir = os.environ["WORKSLOP_APPLY_JOURNAL_DIR"]
    os.makedirs(jdir, exist_ok=True)
    load_plist_tweaks()
    load_mobilegestalt(build="23C5027f", version="26.1")

    dm = dm_mod.DeviceManager()
    dm.get_current_device_name = lambda: "Test iPhone"
    dm.get_current_device_model = lambda: "iPhone14,5"
    dm.get_current_device_version = lambda: "26.6.1"
    dm.get_current_device_build = lambda: "23G83"
    dm.get_current_device_udid = lambda: "TESTUDID-AUDIT5"
    dm._raise_if_unsupported = lambda: None

    at_restore = {}

    async def fake_restore(files, update_label=lambda x: None, **kw):
        # The journal must already name every family, staged, ON DISK
        # before the restore starts (not filled in afterwards).
        with open(dm._current_journal.path) as fh:
            doc = json.load(fh)
        at_restore["tweaks"] = {
            e["tweak_id"]: e["status"] for e in doc["tweaks"]}
        at_restore["files"] = list(files)
        return "OK"
    dm.start_restore = fake_restore

    async def fake_skip_setup(files, restoring_domains):
        return None
    dm.add_skip_setup = fake_skip_setup

    pb = tweaks[TweakID.PosterBoard]
    tpl = tweaks[TweakID.Templates]
    saved_tendies, saved_templates = list(pb.tendies), list(tpl.templates)
    enabled = []
    try:
        tweaks[TweakID.SBHideLowPowerAlerts].set_enabled(True)
        enabled.append(TweakID.SBHideLowPowerAlerts)
        # Gestalt family: enabled but locked on 23G83 -> skipped entry,
        # still recorded (a locked tweak was requested, so it journals).
        tweaks[TweakID.ModelName].set_enabled(True)
        enabled.append(TweakID.ModelName)
        # Content-driven families: queue content, never touch `enabled`.
        pb.tendies = [FakeTendie()]
        tpl.templates = [FakeTemplate()]
        check("posterboard/templates enabled flags stay False",
              pb.enabled is False and tpl.enabled is False)

        dm.apply_changes(lambda x: None, lambda x: None)

        doc = latest_journal("apply")
        by_id = {e["tweak_id"]: e for e in doc["tweaks"]}
        for tid in ("PosterBoard", "Templates", "ModelName",
                    "SBHideLowPowerAlerts"):
            check(f"journal records {tid}", tid in by_id,
                  str(sorted(by_id)))
        check("at restore time all families already on disk",
              at_restore["tweaks"].get("PosterBoard") == "staged"
              and at_restore["tweaks"].get("Templates") == "staged"
              and "ModelName" in at_restore["tweaks"],
              str(at_restore.get("tweaks")))
        check("posterboard entry describes queued content",
              by_id["PosterBoard"]["operation"].get("tendies") == 1,
              str(by_id["PosterBoard"].get("operation")))
        check("posterboard delivered after successful restore",
              by_id["PosterBoard"]["status"] == "delivered-by-restore"
              and by_id["PosterBoard"]["files"],
              str(by_id["PosterBoard"]))
        check("templates delivered after successful restore",
              by_id["Templates"]["status"] == "delivered-by-restore"
              and by_id["Templates"]["files"],
              str(by_id["Templates"]))
        check("gestalt locked skip recorded, not lost",
              by_id["ModelName"]["status"] == "skipped"
              and by_id["ModelName"]["skip_reason"]
              == "mobilegestalt_unsupported_build",
              str(by_id["ModelName"]))
        check("operation success", doc["status"] == "success",
              doc["status"])
    finally:
        pb.tendies, tpl.templates = saved_tendies, saved_templates
        for tid in enabled:
            try:
                tweaks[tid].set_enabled(False)
            except Exception:
                pass


def test_passcode_journal():
    print("\nPasscode write: journal opened before AirLift, finalized after")
    from PySide6.QtWidgets import QApplication
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    import src.gui.ios.passcode_theme as pc_mod

    app = QApplication.instance() or QApplication([])
    jdir = os.environ["WORKSLOP_APPLY_JOURNAL_DIR"]
    os.makedirs(jdir, exist_ok=True)

    seen = {"journal_at_write": None, "done": []}
    fail = {"write": False}

    @asynccontextmanager
    async def fake_lockdown(udid, **kw):
        yield SimpleNamespace(paired=True)

    async def fake_write_files(lockdown, target, staged, log_cb=None):
        # The journal file must already exist, naming the Passcode
        # family as staged, at the moment the device write starts.
        doc = latest_journal("apply")
        entry = [e for e in doc["tweaks"]
                 if e["tweak_id"] == "PasscodeTheme"]
        seen["journal_at_write"] = (doc["status"], entry)
        if fail["write"]:
            raise RuntimeError("airlift boom")
        return {"written": [name for name, _ in staged], "failures": []}

    saved = {name: getattr(pc_mod, name) for name in
             ("parse_passthm", "stage_files", "lockdown_session",
              "write_files")}
    pc_mod.parse_passthm = lambda path: {"1": b"png-bytes"}
    pc_mod.stage_files = lambda keys, **kw: [("en-1---white.png", b"png")]
    pc_mod.lockdown_session = fake_lockdown
    pc_mod.write_files = fake_write_files
    try:
        thread = pc_mod.PasscodeThemeWriteThread(
            udid="TESTUDID-PASSCODE", theme_path="/tmp/fake.passthm",
            key_digits=1, locale="en", lang_opt="", bold="both",
            target_opt="10")
        thread.done.connect(lambda ok, msg: seen["done"].append((ok, msg)))
        thread.run()  # synchronous: run() body, no event loop needed
        check("write reported success", seen["done"]
              and seen["done"][0][0] is True, str(seen["done"]))
        _status, entries = seen["journal_at_write"] or (None, [])
        check("journal named PasscodeTheme before write_files",
              len(entries) == 1 and entries[0]["family"] == "Passcode",
              str(entries))
        check("entry staged before write_files",
              bool(entries) and entries[0]["status"] == "staged",
              str(entries))
        final = latest_journal("apply")
        entry = [e for e in final["tweaks"]
                 if e["tweak_id"] == "PasscodeTheme"][0]
        check("passcode journal finalized success",
              final["status"] == "success", final["status"])
        check("passcode entry delivered",
              entry["status"] == "delivered-by-restore"
              and bool(entry["files"]), str(entry))
        check("thread surfaces journal path",
              bool(thread.journal_path)
              and os.path.exists(thread.journal_path))

        fail["write"] = True
        thread2 = pc_mod.PasscodeThemeWriteThread(
            udid="TESTUDID-PASSCODE", theme_path="/tmp/fake.passthm",
            key_digits=1, locale="en", lang_opt="", bold="both",
            target_opt="10")
        done2 = []
        thread2.done.connect(lambda ok, msg: done2.append(ok))
        thread2.run()
        check("failing write reported as failure", done2 == [False])
        final2 = latest_journal("apply")
        entry2 = [e for e in final2["tweaks"]
                  if e["tweak_id"] == "PasscodeTheme"][0]
        check("failed passcode journal finalized failed",
              final2["status"] == "failed", final2["status"])
        check("failed passcode entry not delivered",
              entry2["status"] == "not-delivered", str(entry2))
    finally:
        for name, fn in saved.items():
            setattr(pc_mod, name, fn)


def main():
    test_main_apply_coverage()
    test_passcode_journal()
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
