#!/usr/bin/env python3
"""Fix Audit 98: Passcode theme write must not fake success.

The write path used to ignore ``result["ok"]`` / ``result["rejected"]``
from ``write_files()`` and label every failure "skipped — they already
exist", then emit success even when the device rejected the session or
dropped mid-write (nothing written, UI green).

Proofs here (offscreen, stubbed AirLift):
* device rejection (ok=False, rejected=True, nothing written)
  -> done(False), an honest "nothing was written" failure, no
  "skipped / already exists" claim, journal finalized *failed*;
* all writes failing without rejection -> done(False), no "skipped";
* ok=False with empty lists (inconsistent report) -> done(False),
  never fake success;
* partial write (some written, some failed) -> done(False) with an
  honest "Partially written: X of Y" status, journal *partial*;
* full ok -> done(True), journal *success*;
* rejection fails fast: later TelephonyUI targets are not attempted.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit98_passcode_write_honest.py
"""
import glob
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0
TMP = tempfile.mkdtemp(prefix="works-audit98-")
os.environ["WORKSLOP_APPLY_JOURNAL_DIR"] = os.path.join(TMP, "journal")

STAGED = [("en-1---white.png", b"png1"), ("en-2---white.png", b"png2")]


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def latest_journal():
    files = sorted(glob.glob(os.path.join(
        os.environ["WORKSLOP_APPLY_JOURNAL_DIR"], "apply-*.json")),
        key=os.path.getmtime)
    with open(files[-1]) as fh:
        return json.load(fh)


def run_thread(pc_mod, fake_write_files, target_opt="10", staged=None):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    staged = STAGED if staged is None else staged

    @asynccontextmanager
    async def fake_lockdown(udid, **kw):
        yield SimpleNamespace(paired=True)

    saved = {name: getattr(pc_mod, name) for name in
             ("parse_passthm", "stage_files", "lockdown_session",
              "write_files")}
    pc_mod.parse_passthm = lambda path: {"1": b"png", "2": b"png"}
    pc_mod.stage_files = lambda keys, **kw: list(staged)
    pc_mod.lockdown_session = fake_lockdown
    pc_mod.write_files = fake_write_files
    try:
        thread = pc_mod.PasscodeThemeWriteThread(
            udid="TESTUDID-AUDIT98", theme_path="/tmp/fake.passthm",
            key_digits=2, locale="en", lang_opt="", bold="both",
            target_opt=target_opt)
        done = []
        thread.done.connect(lambda ok, msg: done.append((ok, msg)))
        thread.run()  # synchronous, like tools/test_audit5_*
        assert len(done) == 1, f"done emitted {len(done)} times: {done}"
        return done[0]
    finally:
        for name, fn in saved.items():
            setattr(pc_mod, name, fn)


def main():
    from PySide6.QtWidgets import QApplication
    import src.gui.ios.passcode_theme as pc_mod

    app = QApplication.instance() or QApplication([])
    os.makedirs(os.environ["WORKSLOP_APPLY_JOURNAL_DIR"], exist_ok=True)

    # 1) Device rejects the session: nothing written -> honest failure.
    async def write_rejected(lockdown, target, staged, log_cb=None):
        return {"targetDirectory": target, "written": [],
                "failures": [name for name, _ in staged],
                "rejected": True, "ok": False}

    ok, msg = run_thread(pc_mod, write_rejected)
    check("rejected write is not success", ok is False, repr(ok))
    check("rejected write says nothing was written",
          "Nothing was written" in msg, msg)
    check("rejected write names the rejection",
          "rejected" in msg, msg)
    check("rejected write never claims skipped/already-exists",
          "skipped" not in msg.lower(), msg)
    doc = latest_journal()
    check("rejected write journal failed", doc["status"] == "failed",
          doc["status"])

    # 2) Every write fails without a rejection -> honest failure too.
    async def write_all_fail(lockdown, target, staged, log_cb=None):
        return {"targetDirectory": target, "written": [],
                "failures": [name for name, _ in staged], "ok": False}

    ok, msg = run_thread(pc_mod, write_all_fail)
    check("all-failed write is not success", ok is False, repr(ok))
    check("all-failed write says nothing was written",
          "Nothing was written" in msg, msg)
    check("all-failed write never claims skipped",
          "skipped" not in msg.lower(), msg)
    doc = latest_journal()
    check("all-failed write journal failed", doc["status"] == "failed",
          doc["status"])

    # 3) Inconsistent report (ok=False, empty lists) -> never success.
    async def write_not_ok(lockdown, target, staged, log_cb=None):
        return {"targetDirectory": target, "written": [], "failures": [],
                "ok": False}

    ok, msg = run_thread(pc_mod, write_not_ok)
    check("ok=False report is not success", ok is False, repr(ok))
    check("ok=False report never claims skipped",
          "skipped" not in msg.lower(), msg)

    # 4) Partial write -> honest partial status (not green success).
    async def write_partial(lockdown, target, staged, log_cb=None):
        return {"targetDirectory": target, "written": [staged[0][0]],
                "failures": [staged[1][0]], "ok": False}

    ok, msg = run_thread(pc_mod, write_partial)
    check("partial write is not reported as success", ok is False, repr(ok))
    check("partial write says partially written",
          "Partially written" in msg, msg)
    check("partial write gives honest counts",
          "1 of 2" in msg, msg)
    check("partial write names the failed file",
          "en-2---white.png" in msg, msg)
    check("partial write never claims skipped",
          "skipped" not in msg.lower(), msg)
    doc = latest_journal()
    check("partial write journal partial", doc["status"] == "partial",
          doc["status"])

    # 5) Full ok -> success.
    async def write_full(lockdown, target, staged, log_cb=None):
        return {"targetDirectory": target,
                "written": [name for name, _ in staged],
                "failures": [], "ok": True}

    ok, msg = run_thread(pc_mod, write_full)
    check("full write is success", ok is True, repr(ok))
    check("full write reports written count", "Wrote 2 file(s)" in msg, msg)
    doc = latest_journal()
    check("full write journal success", doc["status"] == "success",
          doc["status"])

    # 6) Rejection fails fast across targets (all = TelephonyUI 8/9/10).
    calls = {"n": 0}

    async def write_rejected_counted(lockdown, target, staged, log_cb=None):
        calls["n"] += 1
        return await write_rejected(lockdown, target, staged, log_cb)

    ok, msg = run_thread(pc_mod, write_rejected_counted, target_opt="all")
    check("multi-target rejection is not success", ok is False, repr(ok))
    check("rejection stops further targets", calls["n"] == 1,
          str(calls["n"]))

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
