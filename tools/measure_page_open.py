#!/usr/bin/env python3
"""Measure iOS page open latency offscreen (Audit 91 / menu-lag evidence).

Builds the real MainWindow exactly like tools/test_audit_gui_pages.py,
then reports, per iOS stack page:

* ``first_ms``  — first navigation (lazy construction + show + polish);
* ``reshow_ms`` — navigating to the already-built page a second time
  (what the user feels when hopping between menus).

Prints a table sorted by first-open cost. Evidence tool only — it is
not a pass/fail gate; the numbers are for before/after comparison.

Run: ~/wsvenv/bin/python tools/measure_page_open.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-measure-")

from PySide6.QtCore import QSettings, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def main():
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("WorkSlop Desktop")
    # Dismiss any modal a page might try to raise while being built.
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

    t0 = time.perf_counter()
    win = MainWindow(device_manager=DeviceManager(),
                     translator=Translator(app, Settings()))
    win.show()
    app.processEvents()
    startup_ms = (time.perf_counter() - t0) * 1000.0
    print(f"window construction + first show: {startup_ms:.1f} ms")

    count = win.ios_pages.count()
    attrs = [win._ios_page_attrs[i] for i in range(count)]

    first_ms = {}
    for i in range(count):
        t0 = time.perf_counter()
        win.show_ios_page(i)
        app.processEvents()
        first_ms[attrs[i]] = (time.perf_counter() - t0) * 1000.0

    reshow_ms = {}
    for i in range(count):
        # Hop away first so the re-show path (incl. stylesheet layering)
        # actually runs again for this page.
        win.show_ios_page((i + 1) % count)
        app.processEvents()
        t0 = time.perf_counter()
        win.show_ios_page(i)
        app.processEvents()
        reshow_ms[attrs[i]] = (time.perf_counter() - t0) * 1000.0

    print(f"\n{'page':<22} {'first_ms':>10} {'reshow_ms':>10}")
    for attr in sorted(attrs, key=lambda a: -first_ms[a]):
        print(f"{attr:<22} {first_ms[attr]:>10.1f} {reshow_ms[attr]:>10.1f}")
    print(f"{'TOTAL first':<22} {sum(first_ms.values()):>10.1f}")
    print(f"{'TOTAL reshow':<22} {'':>10} {sum(reshow_ms.values()):>10.1f}")


if __name__ == "__main__":
    main()
