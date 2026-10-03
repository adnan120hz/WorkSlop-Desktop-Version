#!/usr/bin/env python3
"""Developer-beta warning checks (v11.5 fix, user report 2026-10-03).

The inherited ``warn_for_dev_beta`` (DeviceBarMixin) showed a modal
``QMessageBox.exec()`` with a hard-coded "iOS 26 beta" text in the
middle of the device-switch flow: on iOS 27 the label was wrong, and
on Linux/Wayland a click on OK killed the app ("The Wayland
connection broke"). This test pins the fixed behaviour against a real
offscreen MainWindow:

* the text names the detected major version (iOS 27 beta / iOS 26 beta),
* the box is deferred (nothing exists synchronously after the call)
  and NON-modal (never exec(), shown modeless, WA_DeleteOnClose),
* it appears at most once per app session per device,
* the trigger set is unchanged (iOS > 26.0 + letter-suffixed build).

Run: QT_QPA_PLATFORM=offscreen python tools/test_beta_warning.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Isolate every QSettings store: never touch the real WorkSlop config.
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-beta-warn-")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


try:
    from PySide6.QtCore import QSettings, Qt, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
except Exception as e:
    print(f"skipped: {type(e).__name__}: {e}")
    raise SystemExit(0)

app = QApplication([])
app.setApplicationName("WorkSlop Desktop")

# With no usbmuxd in this environment, device refresh ends in a modal
# "failed to get device list" dialog; a human would click it away, so
# the test auto-dismisses modal widgets instead of blocking forever.
_modal_killer = QTimer()
_modal_killer.timeout.connect(
    lambda: (QApplication.activeModalWidget().close()
             if QApplication.activeModalWidget() is not None else None))
_modal_killer.start(50)

import src.qt.resources_rc  # noqa: F401,E402
from src.controllers.settings import Settings  # noqa: E402
from src.controllers.translator import Translator  # noqa: E402
from src.devicemanagement.device_manager import DeviceManager  # noqa: E402
from src.gui.main_window import MainWindow  # noqa: E402

qs = QSettings("WorkSlop", "WorkSlop")
qs.setValue("ui/theme", "ios")
qs.sync()
win = MainWindow(device_manager=DeviceManager(),
                 translator=Translator(app, Settings()))
app.processEvents()

# The beta warning must never reach a modal exec(). Record any exec()
# run on a box carrying the beta text (unrelated refresh-error modals
# do not match and are dismissed by the killer above anyway).
beta_exec_calls = []
_orig_exec = QMessageBox.exec


def _counting_exec(self, *a, **k):
    if "You are on iOS" in (self.text() or ""):
        beta_exec_calls.append(self)
    return _orig_exec(self, *a, **k)


QMessageBox.exec = _counting_exec


def set_device(version, build, udid):
    win.device_manager.get_current_device_version = lambda: version
    win.device_manager.get_current_device_build = lambda: build
    win.device_manager.get_current_device_udid = lambda: udid


def beta_boxes():
    return [w for w in win.findChildren(QMessageBox)
            if "You are on iOS" in (w.text() or "")]


def close_beta_boxes():
    for w in beta_boxes():
        w.close()
    app.processEvents()


try:
    print("\niOS 27 beta: right label, deferred, modeless, once per device")
    set_device("27.0", "24A5390f", "FAKE-UDID-27")
    win.warn_for_dev_beta()
    check("nothing shown synchronously (deferred out of the switch flow)",
          beta_boxes() == [])
    app.processEvents()
    boxes = beta_boxes()
    check("exactly one warning box appeared", len(boxes) == 1,
          f"count={len(boxes)}")
    box = boxes[0]
    check("text names iOS 27 beta", "iOS 27 beta" in box.text(), box.text()[:40])
    check("box is not modal", not box.isModal())
    check("no modal widget is active while it is shown",
          QApplication.activeModalWidget() is None)
    check("box deletes itself on close",
          box.testAttribute(Qt.WA_DeleteOnClose))
    check("beta warning never went through modal exec()",
          beta_exec_calls == [])
    close_beta_boxes()
    win.warn_for_dev_beta()
    app.processEvents()
    check("same device is not warned twice in one session",
          beta_boxes() == [])

    print("\niOS 26 beta: label follows the detected major version")
    set_device("26.1", "23B5044i", "FAKE-UDID-26")
    win.warn_for_dev_beta()
    app.processEvents()
    boxes = beta_boxes()
    check("exactly one warning box appeared", len(boxes) == 1,
          f"count={len(boxes)}")
    check("text names iOS 26 beta", "iOS 26 beta" in boxes[0].text(),
          boxes[0].text()[:40])
    close_beta_boxes()

    print("\ntrigger set unchanged")
    set_device("27.0", "24A435", "FAKE-UDID-27F")
    win.warn_for_dev_beta()
    app.processEvents()
    check("final build (digit suffix) stays silent", beta_boxes() == [])
    set_device("26.0", "23A5260n", "FAKE-UDID-26B1")
    win.warn_for_dev_beta()
    app.processEvents()
    check("iOS 26.0 beta stays silent (rule is > 26.0)", beta_boxes() == [])
    set_device("", "", None)
    win.warn_for_dev_beta()
    app.processEvents()
    check("no device stays silent", beta_boxes() == [])
finally:
    QMessageBox.exec = _orig_exec

print(f"\nALL {PASS} CHECKS PASSED")
