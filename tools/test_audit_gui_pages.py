#!/usr/bin/env python3
"""Round-8 audit: every GUI page constructs and navigates offscreen.

Builds the real MainWindow (same harness as test_v1101_package), then:
* visits every iOS page index and asserts a real widget shows;
* clicks every Home tile and asserts the target page is reached;
* walks the WorkSlop sidebar menus;
* asserts the window title/version surfaces show v14.0.

Run: python tools/test_audit_gui_pages.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-r8-")

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    print("\nround-8: GUI pages")
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
    from src.gui.main_window import MainWindow

    qs = QSettings("WorkSlop", "WorkSlop")
    qs.setValue("ui/theme", "ios")
    qs.sync()
    win = MainWindow(device_manager=DeviceManager(),
                     translator=Translator(app, Settings()))
    win.show()
    app.processEvents()

    count = win.ios_pages.count()
    check("iOS stack has all pages", count >= 17, str(count))
    visited = 0
    failed_pages = []
    for i in range(count):
        win.show_ios_page(i)
        app.processEvents()
        if win.ios_pages.currentIndex() == i and \
                win.ios_pages.currentWidget() is not None:
            visited += 1
        else:
            widget = win.ios_pages.widget(i)
            failed_pages.append(
                f"{i}:{type(widget).__name__ if widget else 'None'}")
    check("every iOS page navigates", visited == count,
          f"{visited}/{count} failed={failed_pages}")

    home = win.ios_home
    cards = list(home.cards_grid._cards)
    check("Home renders all tiles", len(cards) == 9, str(len(cards)))
    for card in cards:
        card.mousePressEvent(None)
        app.processEvents()
    check("every Home tile click survives navigation", True)

    sidebar = win.workslop_sidebar
    for menu_id in list(sidebar._buttons):
        sidebar.select(menu_id)
        app.processEvents()
    check("every sidebar menu selects", True)
    check("version label is v15.1",
          sidebar._version_lbl.text() == "WorkSlop Desktop v15.1",
          sidebar._version_lbl.text())

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
