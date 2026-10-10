#!/usr/bin/env python3
"""Offscreen tests for the Reset Tweaks dispatch (Fix A, 2026-10-09).

Two dead-ends are locked shut:

1. ResetDialog must CONSTRUCT when no device info has loaded yet
   (get_resettable_pages used to raise InvalidVersion on the empty
   version string and the button looked completely dead).
2. apply_changes() while another apply runs must TELL the user and
   start nothing — it used to swallow the Reset dialog's OK silently:
   no restore, no restart, no message. The not-busy dispatch itself
   (worker started with the reset pages) is locked too, via a fake
   ApplyThread so no real apply runs.

Run: QT_QPA_PLATFORM=offscreen python tools/test_reset_busy_message.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-reset-busy-")

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("WorkSlop Desktop")
    killer = QTimer()
    killer.timeout.connect(
        lambda: QApplication.activeModalWidget().close()
        if QApplication.activeModalWidget() else None)
    killer.start(50)

    import src.qt.resources_rc  # noqa: F401
    from src.controllers.settings import Settings
    from src.controllers.translator import Translator
    from src.devicemanagement.device_manager import DeviceManager
    from src.gui.dialogs.reset_dialog import ResetDialog
    from src.gui.main_window import MainWindow
    from src.utils.pages import Page

    qs = QSettings("WorkSlop", "WorkSlop")
    qs.setValue("ui/theme", "ios")
    qs.sync()
    win = MainWindow(device_manager=DeviceManager(),
                     translator=Translator(app, Settings()))
    win.show()
    app.processEvents()

    print("\nResetDialog constructs with no device info loaded")
    dialog = ResetDialog(device_manager=win.device_manager,
                         apply_reset=lambda pages: None)
    boxes = dialog.findChildren(QtWidgets.QCheckBox)
    check("dialog built without a device version",
          len(boxes) == 10, f"{len(boxes)} checkboxes")
    dialog.close()

    print("\nbusy: message shown, nothing started, nothing queued")
    info_calls = []
    orig_info = QtWidgets.QMessageBox.information

    def fake_info(parent, title, text, *args, **kwargs):
        info_calls.append((title, text))
        return QtWidgets.QMessageBox.StandardButton.Ok

    QtWidgets.QMessageBox.information = staticmethod(fake_info)
    try:
        win.apply_in_progress = True
        worker_before = getattr(win, "worker_thread", None)
        win.apply_changes([Page.Springboard])
    finally:
        QtWidgets.QMessageBox.information = orig_info
    check("exactly one message was shown", len(info_calls) == 1,
          repr(info_calls))
    check("message says an apply is already in progress",
          any("already applying" in text for _, text in info_calls),
          repr(info_calls))
    check("no worker thread was started",
          getattr(win, "worker_thread", None) is worker_before)
    check("busy flag left untouched", win.apply_in_progress is True)

    print("\nnot busy: reset dispatch starts the worker as before")
    import src.gui.main_window_mixins as mixins

    class FakeApplyThread(QtCore.QThread):
        progress = QtCore.Signal(str)
        alert = QtCore.Signal(object)
        finished_with_result = QtCore.Signal(bool, str)
        request_text = QtCore.Signal(str, str, object)
        choice_prompt = QtCore.Signal(str, str, object)
        backup_finished = QtCore.Signal(str)
        instances = []

        def __init__(self, manager=None, settings=None, reset_pages=None, remove_options=None):
            super().__init__()
            self.manager = manager
            self.settings = settings
            self.reset_pages = reset_pages
            self.remove_options = remove_options
            self.started = False
            FakeApplyThread.instances.append(self)

        def start(self, *args, **kwargs):
            self.started = True

    real_thread = mixins.ApplyThread
    mixins.ApplyThread = FakeApplyThread
    try:
        win.apply_in_progress = False
        win.apply_changes([Page.Springboard, Page.Daemons])
    finally:
        mixins.ApplyThread = real_thread
    check("worker constructed exactly once",
          len(FakeApplyThread.instances) == 1)
    worker = FakeApplyThread.instances[0]
    check("worker got the reset pages",
          worker.reset_pages == [Page.Springboard, Page.Daemons],
          repr(worker.reset_pages))
    check("worker got no removal options by default",
          worker.remove_options is None, repr(worker.remove_options))
    check("worker got the window's device manager",
          worker.manager is win.device_manager)
    check("worker was started", worker.started)
    check("busy flag set by the dispatch", win.apply_in_progress is True)
    win.apply_in_progress = False

    win.close()
    print(f"\nALL {PASS} CHECKS PASSED")


main()
