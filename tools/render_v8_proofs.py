#!/usr/bin/env python3
"""Render the v8 proof screenshots of the final v11 build (offscreen).

Real MainWindow, isolated HOME / QSettings. Renders:
* v8-ui3-daemons.png        Full Nugget Daemons page (dark)
* v8-ui3-posterboard.png    Full Nugget Posterboard page (dark)
* v8-ui3-settings.png       Full Nugget Settings page (dark)
* v8-ui3-settings-picker.png  Settings scrolled to the new stacked
                              interface picker (WorkSlop (Main) /
                              WorkSlop 2 / Nugget)
* v8-ui2-sidebar-backup.png WorkSlop 2 classic sidebar with Backup
* v8-ui3-sidebar-backup.png Full Nugget classic sidebar with Backup
                            (+ dark Daemons behind it)
* v8-ui3-home-beta.png      Full Nugget Home: credits + Beta tester
                            team block above the AutoSave banner
* v8-ui2-home-beta.png      WorkSlop 2 Home: same beta block, light
* v8-ui1-home-beta.png      WorkSlop (Main) Home: same beta block

The classic sidebar buttons are only visible with a device connected
(device-refresh flow); the render forces the connected-state
visibility so the sidebar shows exactly what a connected user sees.
The OS title bar is native chrome and never appears in offscreen
grabs — its dark/light state is proven by tools/test_final_ui_v11.py.

Run: QT_QPA_PLATFORM=offscreen HOME=<tmp> python tools/render_v8_proofs.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-v8-")

from PySide6.QtCore import QSettings, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

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
from src.gui.pages.pages_list import Page  # noqa: E402

# Absolute from this file's location (repo parent's riset tree), so an
# isolated HOME for QSettings cannot redirect the output.
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


# ---- UI-3 (Full Nugget) ------------------------------------------------
win.apply_theme(ThemeManager.FULL_NUGGET)
show_connected_sidebar()
win.on_daemonsPageBtn_clicked()
grab("v8-ui3-daemons.png")
grab("v8-ui3-sidebar-backup.png")
win.on_posterboardPageBtn_clicked()
grab("v8-ui3-posterboard.png")
win.on_settingsPageBtn_clicked()
grab("v8-ui3-settings.png")
_picker_btn = win.ios_settings.interface_buttons[ThemeManager.FULL_NUGGET]
win.ios_settings._scroll.ensureWidgetVisible(_picker_btn)
grab("v8-ui3-settings-picker.png")
win.show_home()
app.processEvents()
grab("v8-ui3-home-beta.png")

# ---- UI-2 (WorkSlop 2 / classic shell) ---------------------------------
win.apply_theme(ThemeManager.CLASSIC)
show_connected_sidebar()
win.show_home()
app.processEvents()
grab("v8-ui2-sidebar-backup.png")
grab("v8-ui2-home-beta.png")

# ---- UI-1 (WorkSlop Main) ----------------------------------------------
win.apply_theme(ThemeManager.IOS)
win.show_home()
app.processEvents()
_beta = win.ios_home.preset_widget._beta_lbl
try:
    win.ios_home._scroll.ensureWidgetVisible(_beta)
except Exception:
    pass
app.processEvents()
grab("v8-ui1-home-beta.png")

print("done:", OUT)
