#!/usr/bin/env python3
"""Fix Audit 54: a disk-space abort must never render as success.

Before: ``_apply_changes`` returned silently on the disk-space abort
paths (``final_alert=None``), so the GUI thread reported
``finished_with_result(True)`` -> "Apply complete!" and the CLI exited
0, while the journal honestly said "aborted".

Proofs here (offscreen, stubbed):
* backend: both abort paths (user chooses Abort; no prompt callback)
  surface an explicit "Apply Aborted" alert and finalize the journal
  "aborted" with the requested tweaks recorded;
* GUI: ApplyThread emits finished_with_result(False, ...) for a
  non-success final alert, (True, "") only for the success alert;
* CLI: ``Nugget apply`` returns 1 for abort/failure/no-alert/raising
  backends and 0 only for the success alert (same pattern as cmd_reset,
  Fix Audit 44).

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit54_abort_honesty.py
"""
import argparse
import contextlib
import glob
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0
TMP = tempfile.mkdtemp(prefix="works-audit54-")
os.environ["WORKSLOP_APPLY_JOURNAL_DIR"] = os.path.join(TMP, "journal")


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def latest_apply_journal():
    files = sorted(glob.glob(os.path.join(
        os.environ["WORKSLOP_APPLY_JOURNAL_DIR"], "apply-*.json")),
        key=os.path.getmtime)
    with open(files[-1]) as fh:
        return json.load(fh)


class FakeAlert:
    def __init__(self, title, txt=""):
        self.title = title
        self.txt = txt or title
        self.icon = None
        self.detailed_txt = None
        self.backup_path = None


def test_backend_abort_alerts():
    print("\nbackend _apply_changes: disk-space abort surfaces as abort")
    from PySide6.QtWidgets import QApplication
    import src.devicemanagement.device_manager as dm_mod
    from src.tweaks.tweaks import tweaks, TweakID
    from src.tweaks.tweak_loader import load_plist_tweaks

    app = QApplication.instance() or QApplication([])
    os.makedirs(os.environ["WORKSLOP_APPLY_JOURNAL_DIR"], exist_ok=True)
    load_plist_tweaks()

    dm = dm_mod.DeviceManager()
    dm.get_current_device_name = lambda: "Test iPhone"
    dm.get_current_device_model = lambda: "iPhone14,5"
    dm.get_current_device_version = lambda: "27.0"
    dm.get_current_device_build = lambda: "24A100"
    dm.get_current_device_udid = lambda: "TESTUDID-AUDIT54"
    dm.get_current_device_partially_supported = lambda: True
    dm._raise_if_unsupported = lambda: None

    async def no_space(update_label=lambda x: None, **kw):
        raise RuntimeError("NotEnoughDiskSpace: device is out of disk space")
    dm._prepare_protective_backup = no_space

    alerts = []
    tweaks[TweakID.SBHideLowPowerAlerts].set_enabled(True)
    try:
        # 1) user chooses Abort at the prompt
        dm.apply_changes(lambda x: None, alerts.append,
                         prompt_choice=lambda title, text: "abort")
        check("abort choice -> one final alert", len(alerts) == 1,
              str(alerts))
        check("abort alert is not success",
              alerts and alerts[0].title == "Apply Aborted",
              str(alerts[0].title if alerts else None))
        check("abort alert says nothing was applied",
              alerts and "Nothing was applied" in alerts[0].txt,
              alerts[0].txt if alerts else "")
        doc = latest_apply_journal()
        check("journal finalized aborted", doc["status"] == "aborted",
              doc["status"])
        check("journal still names the requested tweak",
              any(e["tweak_id"] == "SBHideLowPowerAlerts"
                  for e in doc["tweaks"]), str(doc["tweaks"]))

        # 2) headless: no prompt callback at all
        alerts.clear()
        dm.apply_changes(lambda x: None, alerts.append, prompt_choice=None)
        check("no prompt -> abort alert too",
              len(alerts) == 1 and alerts[0].title == "Apply Aborted",
              str(alerts))
        doc = latest_apply_journal()
        check("headless journal aborted too", doc["status"] == "aborted",
              doc["status"])
    finally:
        tweaks[TweakID.SBHideLowPowerAlerts].set_enabled(False)


class FakeManager:
    def __init__(self, alert=None, raises=False):
        self.last_apply_journal_path = None
        self._alert = alert
        self._raises = raises

    def get_current_device_name(self):
        return "Fake"

    def get_current_device_model(self):
        return "iPhone14,5"

    def get_current_device_version(self):
        return "27.0"

    def get_current_device_build(self):
        return "24A100"

    def get_current_device_udid(self):
        return "TESTUDID-AUDIT54"

    def apply_changes(self, update_label, alert_window, prompt_password=None,
                      prompt_choice=None, on_backup_complete=None):
        if self._raises:
            raise RuntimeError("backend exploded")
        if self._alert is not None:
            alert_window(self._alert)


def _run_apply_thread(manager):
    from src.gui.thread_workers.apply_worker import ApplyThread
    thread = ApplyThread(manager=manager, settings=None)
    results, alerts = [], []
    thread.finished_with_result.connect(
        lambda ok, err: results.append((ok, err)))
    thread.alert.connect(lambda msg: alerts.append(msg))
    thread.run()  # synchronous body; signals fire inline
    return thread, results, alerts


def test_gui_thread_honesty():
    print("\nApplyThread: non-success final alert is not 'Apply complete!'")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    thread, results, _ = _run_apply_thread(FakeManager(
        alert=FakeAlert("Apply Aborted", "Apply aborted: nothing applied")))
    check("abort alert -> finished False",
          results and results[0][0] is False, str(results))
    check("abort alert -> error message carried",
          results and "aborted" in results[0][1].lower(), str(results))
    check("thread.success False on abort", thread.success is False)

    thread, results, _ = _run_apply_thread(FakeManager(
        alert=FakeAlert("Success!", "All done!")))
    check("success alert -> finished True",
          results == [(True, "")], str(results))
    check("thread.success True on success", thread.success is True)

    thread, results, _ = _run_apply_thread(FakeManager(raises=True))
    check("raising backend -> finished False",
          results and results[0][0] is False, str(results))


class FakeDM:
    def __init__(self, alert="success", raises=False):
        import argparse as _ap
        self.pref_manager = _ap.Namespace(
            settings=None, skip_setup=True, auto_reboot=True)
        self.last_apply_journal_path = None
        self._alert = alert
        self._raises = raises

    def apply_changes(self, update_label=None, show_alert=None,
                      prompt_password=None, prompt_choice=None):
        if self._raises:
            raise RuntimeError("backend exploded")
        if show_alert is not None and self._alert != "none":
            title = {"success": "Success!", "abort": "Apply Aborted",
                     "fail": "Error!"}[self._alert]
            show_alert(FakeAlert(title, f"final alert: {title}"))


def _run_cli_apply(dm):
    from src.cli import cmd_apply, common

    class FakeDevice:
        name = "Fake iPhone"
        version = "27.0"
        build = "24A100"
        model = "iPhone14,5"
        udid = "TESTUDID-AUDIT54"

    saved = {name: getattr(common, name) for name in
             ("bootstrap", "make_device_manager", "load_prefs",
              "ensure_device", "ensure_not_killed", "load_core_tweaks",
              "load_default_preset")}
    common.bootstrap = lambda: object()
    common.make_device_manager = lambda settings: dm
    common.load_prefs = lambda dm_, settings: None
    common.ensure_device = lambda dm_, settings, udid=None: FakeDevice()
    common.ensure_not_killed = lambda settings, device=None, dm=None: None
    common.load_core_tweaks = lambda: None
    common.load_default_preset = lambda source, dm_: None
    args = argparse.Namespace(
        udid=None, preset=None, enable=[], disable=[], set=[],
        daemon_disable=[], daemon_enable=[], encrypted_backup=False,
        password=None, no_skip_setup=False, no_reboot=False,
        continue_anyway=False)
    try:
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            try:
                code = cmd_apply.run(args)
            except SystemExit as e:
                code = ("SystemExit", e.code)
    finally:
        for name, fn in saved.items():
            setattr(common, name, fn)
    return code


def test_cli_exit_codes():
    print("\ncmd_apply: honest exit codes")
    check("success alert -> exit 0", _run_cli_apply(FakeDM("success")) == 0)
    check("abort alert -> exit 1", _run_cli_apply(FakeDM("abort")) == 1)
    check("failure alert -> exit 1", _run_cli_apply(FakeDM("fail")) == 1)
    check("no final alert -> exit 1 (success never reported)",
          _run_cli_apply(FakeDM("none")) == 1)
    check("raising backend -> exit 1",
          _run_cli_apply(FakeDM(raises=True)) == 1)


def main():
    test_backend_abort_alerts()
    test_gui_thread_honesty()
    test_cli_exit_codes()
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
