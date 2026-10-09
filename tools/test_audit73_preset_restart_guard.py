#!/usr/bin/env python3
"""Fix Audit 73: Load Preset restart + close guard coverage.

Before: ``load_preset_flow`` restarted the process with no check (it
could kill a restore mid-write), and ``MainWindow.closeEvent``'s guard
did not cover Gestalt apply or full restore.

Proofs here (offscreen, stubbed):
* ``device_operations_running`` (the single shared guard list) names
  Gestalt apply and full restore alongside the old entries;
* ``load_preset_flow`` refuses BEFORE loading/restarting while a
  guarded operation runs, and still loads + restarts when idle;
* ``MainWindow.closeEvent`` asks (and honors Cancel) naming the
  Gestalt apply / full restore that is running.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit73_preset_restart_guard.py
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


class FakeBox:
    """QMessageBox stand-in recording every dialog."""

    Yes = 1
    Cancel = 2

    class StandardButton:
        Yes = 1
        Cancel = 2

    calls = []
    question_reply = 1

    @classmethod
    def reset(cls):
        cls.calls = []
        cls.question_reply = cls.StandardButton.Yes

    @classmethod
    def question(cls, parent, title, text, *a, **kw):
        cls.calls.append(("question", title, text))
        return cls.question_reply

    @classmethod
    def warning(cls, parent, title, text, *a, **kw):
        cls.calls.append(("warning", title, text))

    @classmethod
    def information(cls, parent, title, text, *a, **kw):
        cls.calls.append(("information", title, text))

    @classmethod
    def critical(cls, parent, title, text, *a, **kw):
        cls.calls.append(("critical", title, text))


class FakeSettings:
    def __init__(self):
        self.values = {}

    def setValue(self, key, value):
        self.values[key] = value

    def value(self, key, default=None, type=None):
        return self.values.get(key, default)


class FakeDM:
    def get_current_device_version(self):
        return "26.6.1"

    def get_current_device_model(self):
        return "iPhone14,5"

    def get_current_device_build(self):
        return "23G83"


class FakePM:
    def __init__(self):
        self.last_skipped = []
        self.load_called = False

    def get_preset_metadata(self, name):
        return {"description": "d", "device_model": "iPhone14,5",
                "ios_version": "26.6.1"}

    def preset_hidden_feature_names(self, name, hotload, **kw):
        return []

    def preset_has_daemon_changes(self, name):
        return False

    def load_preset(self, name, **kw):
        self.load_called = True
        return True


def fake_window(**flags):
    window = SimpleNamespace(
        apply_in_progress=False,
        _cache_restore_in_progress=False,
        _gestalt_apply_in_progress=False,
        _full_restore_in_progress=False,
        _gestalt_apply_thread=None,
        _full_restore_thread=None,
        _ios_page_objs={},
        settings=FakeSettings(),
        device_manager=FakeDM(),
    )
    window._sync_settings = lambda: None
    for key, value in flags.items():
        setattr(window, key, value)
    return window


def test_guard_list():
    print("\ndevice_operations_running: shared guard list")
    from src.gui.main_window_mixins import device_operations_running

    check("idle window -> no operations",
          device_operations_running(fake_window()) == [])
    ops = device_operations_running(fake_window(
        _gestalt_apply_in_progress=True))
    check("gestalt apply covered", ops == ["MobileGestalt apply"], str(ops))
    ops = device_operations_running(fake_window(
        _full_restore_in_progress=True))
    check("full restore covered", ops == ["full restore"], str(ops))
    ops = device_operations_running(fake_window(
        apply_in_progress=True, _gestalt_apply_in_progress=True,
        _full_restore_in_progress=True))
    check("combined operations all named",
          ops == ["apply/reset", "MobileGestalt apply", "full restore"],
          str(ops))


def test_load_preset_flow():
    print("\nload_preset_flow: restart guard before restart")
    import src.gui.ios.preset_menu as preset_mod

    saved_box, saved_restart = preset_mod.QMessageBox, preset_mod.restart_app
    restarts = []
    preset_mod.QMessageBox = FakeBox
    preset_mod.restart_app = lambda: restarts.append(True)
    try:
        # Gestalt apply running -> refuse before load/restart.
        FakeBox.reset()
        pm = FakePM()
        result = preset_mod.load_preset_flow(
            None, fake_window(_gestalt_apply_in_progress=True), pm, "P1")
        check("gestalt running -> load refused", result is False)
        check("gestalt running -> preset NOT loaded", not pm.load_called)
        check("gestalt running -> NO restart", restarts == [])
        check("refusal explains itself",
              any(kind == "warning" and "MobileGestalt apply" in text
                  and "Nothing was loaded" in text
                  for kind, _t, text in FakeBox.calls),
              str(FakeBox.calls))

        # Full restore running -> same refusal.
        FakeBox.reset()
        pm = FakePM()
        result = preset_mod.load_preset_flow(
            None, fake_window(_full_restore_in_progress=True), pm, "P1")
        check("full restore running -> load refused", result is False)
        check("full restore running -> preset NOT loaded",
              not pm.load_called)
        check("full restore running -> NO restart", restarts == [])

        # Idle -> loads and restarts exactly like before.
        FakeBox.reset()
        pm = FakePM()
        result = preset_mod.load_preset_flow(None, fake_window(), pm, "P1")
        check("idle -> load succeeds", result is True)
        check("idle -> preset loaded", pm.load_called)
        check("idle -> restart happened", restarts == [True])
    finally:
        preset_mod.QMessageBox, preset_mod.restart_app = saved_box, saved_restart


def test_close_event():
    print("\nMainWindow.closeEvent: gestalt/full-restore ask + honor Cancel")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import src.gui.main_window as main_mod

    saved_box = main_mod.QtWidgets.QMessageBox
    main_mod.QtWidgets.QMessageBox = FakeBox
    try:
        for flag, label in (("_gestalt_apply_in_progress",
                             "MobileGestalt apply"),
                            ("_full_restore_in_progress", "full restore")):
            FakeBox.reset()
            FakeBox.question_reply = FakeBox.StandardButton.Cancel
            win = main_mod.MainWindow.__new__(main_mod.MainWindow)
            win.apply_in_progress = False
            win._cache_restore_in_progress = False
            win._gestalt_apply_in_progress = False
            win._full_restore_in_progress = False
            setattr(win, flag, True)
            win._ios_page_objs = {}
            win.worker_thread = None
            win._cache_restore_thread = None
            win._gestalt_apply_thread = None
            win._full_restore_thread = None
            win.refresh_worker_thread = None
            ignored = []
            event = SimpleNamespace(ignore=lambda: ignored.append(True))
            main_mod.MainWindow.closeEvent(win, event)
            check(f"closeEvent asks naming {label}",
                  any(kind == "question" and label in text
                      for kind, _t, text in FakeBox.calls),
                  str(FakeBox.calls))
            check(f"closeEvent honors Cancel for {label}",
                  ignored == [True])
    finally:
        main_mod.QtWidgets.QMessageBox = saved_box


def main():
    test_guard_list()
    test_load_preset_flow()
    test_close_event()
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
