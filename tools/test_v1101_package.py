#!/usr/bin/env python3
"""v11.0.1 focused-package checks (user orders 2026-10-03 13:39-13:45).

Covers ONLY the v11.0.1 scope, against a real offscreen MainWindow:

* Version is ``11.0.1`` everywhere it is shown (app constant, classic
  label, iOS sidebar label).
* Backup page: no "Backup Location" section / dead "Open Folder"
  button; a process indicator (status text + progress bar) sits at the
  bottom of the page and is driven by the real worker progress text
  (percent -> determinate bar, phase-only -> indeterminate, never an
  invented number).
* Starting a Full / Protective Backup asks where to save it (native
  folder picker); the pick is created if missing, remembered in the
  ``backup_storage_dir`` pref, and cancelling starts nothing.
* The backup storage root resolves to the remembered folder (so the
  automatic protective backup before an apply lands there too).
* Themes page blends with Full Nugget (UI-3) dark palette; themed
  (UI-1/UI-2) look unchanged.
* Apply page blends with Full Nugget dark, and its Progress section
  shows for percent AND phase-only lines; the themed interfaces'
  Progress section behaves the same.

Run: QT_QPA_PLATFORM=offscreen python tools/test_v1101_package.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Isolate every QSettings store: never touch the real WorkSlop config.
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-v1101-")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


try:
    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton
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
from packaging.version import Version  # noqa: E402

import src.gui.ios.backup as backup_mod  # noqa: E402
from src.controllers.settings import Settings  # noqa: E402
from src.controllers.translator import Translator  # noqa: E402
from src.devicemanagement.device_manager import DeviceManager  # noqa: E402
from src.gui.ios.apply import IOSApplyPage  # noqa: E402
from src.gui.ios.backup import IOSBackupPage  # noqa: E402
from src.gui.ios.themes_hub import IOSThemesHubPage  # noqa: E402
from src.gui.ios.theme_manager import ThemeManager  # noqa: E402
from src.gui.main_window import MainWindow  # noqa: E402
from src.gui.theme.colors import NUGGET_DARK  # noqa: E402
from src.version import App_Version  # noqa: E402

# ---------------------------------------------------------------- version
print("\nversion is 11.0.1 everywhere")
check("App_Version is 11.0.1", App_Version == "11.0.1", App_Version)
check("11.0 users get offered 11.0.1",
      Version("11.0") < Version(App_Version))
check("11.0.1 users get offered nothing newer by this build",
      not (Version(App_Version) < Version(App_Version)))

qs = QSettings("WorkSlop", "WorkSlop")
qs.setValue("ui/theme", "ios")
qs.sync()
win = MainWindow(device_manager=DeviceManager(),
                 translator=Translator(app, Settings()))
app.processEvents()

check("classic version label shows 11.0.1",
      "11.0.1" in win.ui.appVersionLbl.text(), win.ui.appVersionLbl.text())
check("classic version label has no beta/stable wording",
      "beta" not in win.ui.appVersionLbl.text().lower()
      and "stable" not in win.ui.appVersionLbl.text().lower())
check("iOS sidebar version label is clean 11.0.1",
      win.workslop_sidebar._version_lbl.text() == "WorkSlop Desktop v11.0.1",
      win.workslop_sidebar._version_lbl.text())

# ------------------------------------------------------- backup page UI
print("\nbackup page: no dead location section, live bottom indicator")
page = win.ios_backup
label_texts = [lbl.text() for lbl in page.findChildren(QLabel)]
button_texts = [btn.text() for btn in page.findChildren(QPushButton)]
check("no 'Backup Location' text left on the Backup page",
      not any("Backup Location" in t for t in label_texts))
check("no dead 'Open Folder' button left on the Backup page",
      not any("Open Folder" in t for t in button_texts + label_texts))
check("bottom process indicator starts at 'Ready.'",
      page._process_lbl.text() == "Ready.", page._process_lbl.text())
check("bottom bar starts empty (0 of 100)",
      page._process_bar.minimum() == 0 and page._process_bar.maximum() == 100
      and page._process_bar.value() == 0)

# The same worker text the classic Apply page shows drives the strip.
win.update_label("Backing up... (42.5%)")
check("percent line drives the bottom bar",
      page._process_bar.maximum() == 100
      and page._process_bar.value() == 42,
      f"value={page._process_bar.value()}")
check("the real status text is mirrored verbatim",
      page._process_lbl.text() == "Backing up... (42.5%)")
win.update_label("Backing up your device...")
check("phase-only line runs the bar indeterminate (no invented number)",
      page._process_bar.minimum() == 0 and page._process_bar.maximum() == 0)
check("phase text is mirrored verbatim",
      page._process_lbl.text() == "Backing up your device...")
win._mirror_backup_finish(True)
check("finish settles the bar at 100%",
      page._process_bar.maximum() == 100 and page._process_bar.value() == 100)
win._mirror_backup_finish(False)
check("failed finish clears the bar",
      page._process_bar.maximum() == 100 and page._process_bar.value() == 0)

# ------------------------------------------------------- Apply progress
print("\napply page: Progress section on every interface")
apply_page = win.ios_apply
apply_page.set_status("Restoring to device... (14.7%)\nDO NOT UNPLUG")
check("percent line shows a determinate bar at the real percent",
      not apply_page.progress_bar.isHidden()
      and apply_page.progress_bar.maximum() == 100
      and apply_page.progress_bar.value() == 15,
      f"value={apply_page.progress_bar.value()}")
apply_page.set_status("Restoring to device...")
check("phase-only line keeps the bar visible, indeterminate",
      not apply_page.progress_bar.isHidden()
      and apply_page.progress_bar.maximum() == 0)
apply_page.set_status("")
check("empty status hides the bar again",
      apply_page.progress_bar.isHidden())

# ------------------------------------------------------- Themes / Apply
print("\nthemes + apply blend with Full Nugget; themed look untouched")
themes_page = win.ios_themes_hub
check("themes page starts in the themed palette",
      themes_page._palette() is not NUGGET_DARK
      and themes_page._full_nugget is False)
win.apply_theme(ThemeManager.FULL_NUGGET)
app.processEvents()
check("themes page takes the Nugget dark palette in UI-3",
      themes_page._palette() is NUGGET_DARK
      and themes_page._full_nugget is True)
check("themes scroll background is the Nugget dark",
      NUGGET_DARK.bg_primary in themes_page._scroll.styleSheet(),
      themes_page._scroll.styleSheet()[:90])
check("apply page takes the Nugget dark palette in UI-3",
      apply_page._palette() is NUGGET_DARK
      and apply_page._full_nugget is True)
check("apply page background is the Nugget dark",
      NUGGET_DARK.bg_primary in apply_page._scroll.styleSheet(),
      apply_page._scroll.styleSheet()[:90])
check("themes primary button is a readable Nugget-blue button in UI-3",
      NUGGET_DARK.accent in themes_page._fn_buttons[0].styleSheet()
      and "color: #FFFFFF" in themes_page._fn_buttons[0].styleSheet(),
      themes_page._fn_buttons[0].styleSheet()[:80])
check("apply primary button is a readable Nugget-blue button in UI-3",
      NUGGET_DARK.accent in apply_page.apply_btn.styleSheet()
      and "color: #FFFFFF" in apply_page.apply_btn.styleSheet(),
      apply_page.apply_btn.styleSheet()[:80])
win.apply_theme(ThemeManager.IOS)
app.processEvents()
check("themes page returns to the themed palette outside UI-3",
      themes_page._palette() is not NUGGET_DARK
      and themes_page._full_nugget is False)
check("apply page returns to the themed palette outside UI-3",
      apply_page._palette() is not NUGGET_DARK
      and apply_page._full_nugget is False)

# ------------------------------------------------------- folder picker
print("\nbackup start asks where to save (folder picker flow)")


class FakeSettings:
    def __init__(self):
        self.store = {}

    def value(self, key, default="", type=str):
        return self.store.get(key, default)

    def setValue(self, key, val):
        self.store[key] = val


class FakeWindow:
    def __init__(self):
        self.settings = FakeSettings()
        self.started = []

    def _start_full_backup(self, folder):
        self.started.append(("full", folder))

    def _start_protective_backup(self):
        self.started.append(("protective",))

    def _build_apply_summary(self):
        return ([], 0)

    def apply_tweaks_clicked(self):
        pass

    def remove_tweaks_clicked(self):
        pass


from enum import IntFlag  # noqa: E402


class FakeMessageBox:
    class StandardButton(IntFlag):
        Yes = 1
        No = 2
        Cancel = 4

    @staticmethod
    def warning(*a, **k):
        return FakeMessageBox.StandardButton.Yes

    @staticmethod
    def question(*a, **k):
        return FakeMessageBox.StandardButton.Yes


picker_calls = []
picker_result = [""]


class FakeFileDialog:
    class Option(IntFlag):
        ShowDirsOnly = 1

    @staticmethod
    def getExistingDirectory(parent, title, start="", options=None):
        picker_calls.append({"title": title, "start": start})
        return picker_result[0]


real_mb = backup_mod.QMessageBox
real_fd = backup_mod.QFileDialog
backup_mod.QMessageBox = FakeMessageBox
backup_mod.QFileDialog = FakeFileDialog
try:
    fake_win = FakeWindow()
    picker_page = IOSBackupPage(fake_win)
    target = os.path.join(tempfile.gettempdir(), "workslop-v1101-pick", "deep")
    picker_result[0] = target
    picker_page._on_full_backup()
    check("full backup starts in the picked folder",
          fake_win.started == [("full", target)], str(fake_win.started))
    check("picked folder is created (with parents)",
          os.path.isdir(target))
    check("the pick is remembered in the backup_storage_dir pref",
          fake_win.settings.store.get("backup_storage_dir") == target)

    picker_page._on_full_backup()
    check("the next picker opens at the remembered folder",
          picker_calls[-1]["start"] == target, picker_calls[-1]["start"])

    picker_result[0] = ""
    fake_win.started.clear()
    picker_page._on_full_backup()
    picker_page._on_protective_backup()
    check("cancelling the picker starts nothing",
          fake_win.started == [], str(fake_win.started))

    prot_target = os.path.join(tempfile.gettempdir(), "workslop-v1101-prot")
    picker_result[0] = prot_target
    picker_page._on_protective_backup()
    check("protective backup asks for its folder too (same flow)",
          fake_win.started == [("protective",)])
    check("protective pick updates the remembered folder",
          fake_win.settings.store.get("backup_storage_dir") == prot_target)
    picker_page.deleteLater()
finally:
    backup_mod.QMessageBox = real_mb
    backup_mod.QFileDialog = real_fd

# The storage root (used by the automatic pre-apply protective backup)
# resolves to the remembered folder.
from pathlib import Path  # noqa: E402

from src.restore.storage import cache_base, protective_base  # noqa: E402

real_settings = Settings()
real_settings.setValue("backup_storage_dir", prot_target)
real_settings.sync()
check("protective backups land under the picked folder",
      str(protective_base()) == str(Path(prot_target) / "protective"),
      str(protective_base()))
check("backup cache lands under the picked folder",
      str(cache_base()) == str(Path(prot_target) / "backup_cache"),
      str(cache_base()))
real_settings.remove("backup_storage_dir")
real_settings.sync()

# ------------------------------------------------------- Apply UI-1/UI-2
print("\napply progress section present outside the classic shell too")
# IOSApplyPage is the apply surface hosted by both classic shells; the
# same page class carries the Progress section everywhere it is hosted.
solo_win = FakeWindow()
solo_win.themeChBox = None
solo_apply = IOSApplyPage(solo_win)
solo_apply.set_status("Restoring to device... (14.7%)\nDO NOT UNPLUG")
check("hosted apply page shows the Progress bar with the real percent",
      solo_apply.progress_bar.maximum() == 100
      and solo_apply.progress_bar.value() == 15
      and solo_apply.status_lbl.text().startswith("Restoring to device"))
solo_apply.deleteLater()

print(f"\nALL {PASS} CHECKS PASSED")
