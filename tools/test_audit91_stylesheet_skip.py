#!/usr/bin/env python3
"""Audit 91: identical global stylesheet is not re-applied per page.

``MainWindow._prepend_global_qss`` layers the global sheet under each
page's own sheet. Re-setting an identical sheet re-polishes the
page's whole subtree, so the helper now skips the call when the
composed sheet is byte-identical to what the page already wears. This
test spies on the Settings page's setStyleSheet: a repeat layer with
nothing changed must not touch the widget, while a genuinely changed
composition still applies.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit91_stylesheet_skip.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-a91-")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


from PySide6.QtCore import QSettings, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setApplicationName("WorkSlop Desktop")
killer = QTimer()
killer.timeout.connect(
    lambda: QApplication.activeModalWidget().close()
    if QApplication.activeModalWidget() else None)
killer.start(50)

import src.qt.resources_rc  # noqa: E402,F401
from src.controllers.settings import Settings  # noqa: E402
from src.controllers.translator import Translator  # noqa: E402
from src.devicemanagement.device_manager import DeviceManager  # noqa: E402
from src.gui.main_window import MainWindow  # noqa: E402
from src.gui.theme import t  # noqa: E402

qs = QSettings("WorkSlop", "WorkSlop")
qs.setValue("ui/theme", "ios")
qs.sync()
win = MainWindow(device_manager=DeviceManager(),
                 translator=Translator(app, Settings()))
win.show()
app.processEvents()

win.show_ios_page(4)  # Settings, built + layered once
app.processEvents()
page = win.ios_settings
check("page wears the global sheet first",
      page.styleSheet().startswith(t("global")[:80]))

calls = []
real_set = page.setStyleSheet


def spy(sheet):
    calls.append(sheet)
    real_set(sheet)


page.setStyleSheet = spy
win._prepend_global_qss(page, "ios_settings")
page.setStyleSheet = real_set
check("identical re-layer skipped (no setStyleSheet call)", not calls,
      f"{len(calls)} calls")

# A changed composition must still apply: perturb the sheet, re-layer.
page.setStyleSheet(page.styleSheet() + "\n/* audit91 */")
calls.clear()
page.setStyleSheet = spy
win._prepend_global_qss(page, "ios_settings")
page.setStyleSheet = real_set
check("changed composition still applied", len(calls) == 1,
      f"{len(calls)} calls")
check("global sheet still on top after re-layer",
      page.styleSheet().startswith(t("global")[:80]))

# Page level: Settings refreshes on every show (Audit 57) and used to
# re-polish its scroll root + cards every time. With an unchanged
# palette, a refresh must not re-set the scroll area's sheet at all,
# while a palette change still lands.
scroll_calls = []
real_scroll_set = page._scroll.setStyleSheet


def scroll_spy(sheet):
    scroll_calls.append(sheet)
    real_scroll_set(sheet)


page._scroll.setStyleSheet = scroll_spy
page.refresh()
page._scroll.setStyleSheet = real_scroll_set
check("settings refresh skips identical scroll sheet", not scroll_calls,
      f"{len(scroll_calls)} calls")

print(f"\nALL {PASS} CHECKS PASSED")
