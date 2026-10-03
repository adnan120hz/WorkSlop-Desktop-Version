#!/usr/bin/env python3
"""Render the v9 proof screenshots of the v11.0.1 package (offscreen).

Real MainWindow, isolated HOME / QSettings. Renders:
* v9-backup-page.png       Backup page: no "Backup Location" section,
                           process indicator pinned to the bottom
                           (idle: "Ready." + empty bar)
* v9-themes-ui3.png        Themes page in Full Nugget (UI-3) dark
* v9-apply-ui1-progress.png  Apply page (main UI) with the Progress
                           section fed a real-format status line
* v9-apply-ui2-progress.png  Apply page in the WorkSlop 2 shell, same
* v9-apply-ui3.png         Apply page in Full Nugget dark, same
* v9-folder-picker.png     The folder picker shown when a backup
                           starts (Qt-rendered: offscreen cannot show
                           the native OS file dialog; the app code
                           itself uses the native dialog — this grab
                           only shows what folder choice looks like)

The status line fed to the Apply pages ("Restoring to device...
(14.7%) / DO NOT UNPLUG") is the exact text the device backend
reports during a restore; it is fed here only to render the proof —
the widget invents nothing at runtime.

Run: QT_QPA_PLATFORM=offscreen HOME=<tmp> python tools/render_v9_proofs.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-v9-")

from PySide6.QtCore import QSettings, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

app = QApplication([])
app.setApplicationName("WorkSlop Desktop")

# With no usbmuxd in this environment, device refresh ends in a modal
# "failed to get device list" dialog; auto-dismiss it like a user would.
_modal_killer = QTimer()
_modal_killer.timeout.connect(
    lambda: (QApplication.activeModalWidget().close()
             if QApplication.activeModalWidget() is not None else None))
_modal_killer.start(50)

import src.qt.resources_rc  # noqa: F401,E402
from src.controllers.settings import Settings  # noqa: E402
from src.controllers.translator import Translator  # noqa: E402
from src.devicemanagement.device_manager import DeviceManager  # noqa: E402
from src.gui.ios.theme_manager import ThemeManager  # noqa: E402
from src.gui.main_window import MainWindow  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(os.path.dirname(_REPO), "riset", "wave11", "ui-3ui-proof")
os.makedirs(OUT, exist_ok=True)

qs = QSettings("WorkSlop", "WorkSlop")
qs.setValue("ui/theme", "ios")
qs.sync()
win = MainWindow(device_manager=DeviceManager(),
                 translator=Translator(app, Settings()))
win.resize(1300, 950)
win.show()
app.processEvents()

STATUS = "Restoring to device... (14.7%)\nDO NOT UNPLUG"


def grab(name):
    app.processEvents()
    ok = win.grab().save(os.path.join(OUT, name))
    print(("saved " if ok else "FAILED ") + name)


def show_connected_sidebar():
    """Sidebar buttons as they appear with a device connected."""
    for name in ("sidebarDiv1", "posterboardPageBtn",
                 "springboardOptionsPageBtn", "internalOptionsPageBtn",
                 "liquidGlassPageBtn", "daemonsPageBtn", "iconThemesPageBtn",
                 "gestaltPageBtn", "sidebarDiv2", "applyPageBtn",
                 "backupPageBtn", "statusBarPageBtn"):
        w = getattr(win.ui, name, None)
        if w is not None:
            w.show()


# ---- Backup page (UI-1): no location section, bottom indicator --------
win.apply_theme(ThemeManager.IOS)
win.show_ios_page(13)
app.processEvents()
grab("v9-backup-page.png")

# ---- Themes in UI-3 (Full Nugget dark) ---------------------------------
win.apply_theme(ThemeManager.FULL_NUGGET)
show_connected_sidebar()
win.show_ios_page(14)
app.processEvents()
grab("v9-themes-ui3.png")

# ---- Apply in UI-3 (Nugget dark) with the Progress section -------------
win.on_applyPageBtn_clicked()
win.ios_apply.set_status(STATUS)
app.processEvents()
grab("v9-apply-ui3.png")

# ---- Apply in UI-2 (classic WorkSlop shell) with Progress --------------
win.apply_theme(ThemeManager.CLASSIC)
show_connected_sidebar()
win.on_applyPageBtn_clicked()
win.ios_apply.set_status(STATUS)
app.processEvents()
grab("v9-apply-ui2-progress.png")

# ---- Apply in UI-1 (main UI) with Progress ------------------------------
win.apply_theme(ThemeManager.IOS)
win.show_ios_page(6)
win.ios_apply.set_status(STATUS)
app.processEvents()
grab("v9-apply-ui1-progress.png")
win.ios_apply.set_status("")

# ---- Folder picker (Qt-rendered stand-in for the native dialog) ---------
dlg = QFileDialog(win, "Where to save the full backup")
dlg.setFileMode(QFileDialog.FileMode.Directory)
dlg.setOption(QFileDialog.Option.ShowDirsOnly, True)
dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
dlg.setDirectory(os.path.expanduser("~"))
dlg.resize(760, 520)
dlg.show()
app.processEvents()
ok = dlg.grab().save(os.path.join(OUT, "v9-folder-picker.png"))
print(("saved " if ok else "FAILED ") + "v9-folder-picker.png")
dlg.close()

print("done:", OUT)
