#!/usr/bin/env python3
"""Fix Audit 24: the App Data page never pops a modal on open.

Opening the page runs ``showEvent -> refresh_apps``; with no device
that used to raise a blocking ``QMessageBox.warning``. The four
read-path click flows that raised modals — Refresh with no device,
Refresh fetch error, app-click browse error (the backup offer), and
backup-read failure — now render inline on the page (status label +
an inline "Read via device backup" button). Reading behaviour is
unchanged: the button starts the same per-app backup read.

The destructive Delete confirmation stays a modal on purpose: it is
user-initiated, not a page-open dialog.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python \
    tools/test_audit24_appdata_inline.py
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


from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import src.gui.ios.appdata as appdata_mod  # noqa: E402
from src.gui.ios.appdata import IOSAppDataPage  # noqa: E402

# Any read-path modal is a failure: record instead of showing.
MODAL_CALLS = []
for _name in ("warning", "information", "critical", "question"):
    setattr(appdata_mod.QMessageBox, _name,
            classmethod(lambda cls, *a, _n=_name, **k:
                        MODAL_CALLS.append(_n)))


def make_page(udid=""):
    device = SimpleNamespace(udid=udid) if udid else None
    window = SimpleNamespace(device_manager=SimpleNamespace(
        data_singleton=SimpleNamespace(current_device=device)))
    page = IOSAppDataPage(window)
    return page


print("\npage open with no device: inline status, no modal")
page = make_page("")
page.show()
app.processEvents()
check("no modal raised on page open", MODAL_CALLS == [], repr(MODAL_CALLS))
check("inline status names the problem",
      "No device connected" in page.status_lbl.text(),
      page.status_lbl.text())
check("status label is visible", page.status_lbl.isVisible())

print("\nrefresh fetch error: inline, no modal")
page._on_apps_error("fetch boom")
check("error shown inline", page.status_lbl.text() == "fetch boom")
check("still no modal", MODAL_CALLS == [], repr(MODAL_CALLS))

print("\napp-click browse error: inline backup offer, same read behind it")
page._on_browse_error("com.example.App", "house arrest denied")
check("offer names the app and the error",
      "com.example.App" in page.status_lbl.text()
      and "house arrest denied" in page.status_lbl.text(),
      page.status_lbl.text())
check("backup button visible", page._backup_btn.isVisible())
check("pending bundle recorded",
      page._pending_backup_bundle == "com.example.App")
check("still no modal", MODAL_CALLS == [], repr(MODAL_CALLS))

started = []
page._browse_via_backup = lambda b: started.append(b)
page._backup_btn.click()
app.processEvents()
check("inline button starts the same backup read",
      started == ["com.example.App"], repr(started))
check("prompt hidden after click", not page._backup_btn.isVisible())

print("\nbackup-read failure: inline, no modal")
page2 = make_page("UDID1")
page2._on_backup_error("com.example.App", "backup boom")
check("failure shown inline",
      "Backup read failed" in page2.status_lbl.text()
      and "backup boom" in page2.status_lbl.text(),
      page2.status_lbl.text())
check("still no modal", MODAL_CALLS == [], repr(MODAL_CALLS))

print("\nsource: read paths contain no QMessageBox call")
src = open(os.path.join(os.path.dirname(__file__), "..",
                        "src", "gui", "ios", "appdata.py"),
           encoding="utf-8").read()
check("only the Delete confirmation remains modal",
      src.count("QMessageBox.question") == 1
      and "QMessageBox.warning" not in src
      and "QMessageBox.information" not in src)

print(f"\nALL {PASS} CHECKS PASSED")
