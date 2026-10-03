#!/usr/bin/env python3
"""Offscreen checks for the Wave 11 dual-interface shell.

Contract (user order 2026-10-03):

* Main UI = WorkSlop v4: light 216 px sidebar rail, iOS-style page stack,
  and the WorkSlop menu set (Home / Tweaks / MobileGestalt / Wallpaper /
  Backup / App Data / Themes / Settings).
* Second UI = classic Nugget shell: generated device bar + sidebar and
  classic Home/Daemons pages, with the classic chrome icons swapped to
  the WorkSlop ``ws-*.svg`` set.
* The Wave 10 modern shell (3uTools-style top bar / left device panel /
  footer) is archived code and is not instantiated by ``MainWindow``.
* ``ThemeManager`` defaults a fresh install to the WorkSlop UI; the
  first-launch picker and the Settings interface switch both persist the
  same ``ui/theme`` choice.
* About carries the English Nugget UI reference (user order
  2026-10-03) and no "3uTools" credit appears anywhere in the app; the
  visible app version is exactly ``11.0``.
* Pages are the real v4.0 pages restored from commit ``4f44415`` (hero
  Home with 9 feature tiles, SKY palette, white rail, v4 SkyBackground)
  integrated with the current backend — not the Wave 10 rebuild pages.

Run: QT_QPA_PLATFORM=offscreen python tools/test_wave10_ui_rebuild.py
"""
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Isolate every QSettings store: the dual-UI checks flip ui/theme and must
# never touch the developer's real WorkSlop configuration.
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-ui-test-")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


try:
    from PySide6.QtCore import QEvent, QFile, QSettings, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import (
        QApplication, QLabel, QMainWindow, QToolButton)
except Exception as e:
    print(f"skipped: {type(e).__name__}: {e}")
    raise SystemExit(0)

app = QApplication([])
app.setApplicationName("WorkSlop Desktop")

try:
    import src.qt.resources_rc  # noqa: F401
except Exception:
    pass

from src.gui.dialogs.dialogs import AboutProgramDialog
from src.gui.interface_picker import InterfacePickerDialog
from src.gui.ios.home import IOSHomePage
from src.gui.ios.phone_frame import (
    PhoneFrame, notch_type_for_product, _DOCK_APPS, _HOME_GRID_APPS)
from src.gui.ios.sidebar import MENUS, SIDEBAR_WIDTH, WorkSlopSidebar
from src.gui.ios.sky_bg import FLOAT_COUNT, FLOAT_TINTS, SkyBackground
from src.gui.ios.theme_manager import ThemeManager
from src.gui.main_window import _HIDDEN_THEMED_ICONS
from src.gui.main_window_mixins import NavigationMixin
from src.gui.theme import ColorThemeManager, t
from src.version import App_Build, App_Version


class _Settings:
    def value(self, *_args, **_kwargs):
        return ""

    def setValue(self, *_args, **_kwargs):
        pass

    def sync(self):
        pass


class _Device:
    name = "iPhone 14"
    connected_via_usb = True
    version = "26.6.1"
    build = "23G83"


class _DeviceManager:
    devices = [_Device()]
    current_device_index = 0

    def get_current_device_udid(self):
        return "wave11-offscreen-udid-0001"

    def get_current_device_version(self):
        return "26.6.1"

    def get_current_device_build(self):
        return "23G83"

    def get_current_device_model(self):
        return "iPhone14,5"

    def get_current_device_name(self):
        return "iPhone 14"

    def get_current_device_is_supported_by_fork(self):
        return True

    def get_current_device_partially_supported(self):
        return False

    data_singleton = SimpleNamespace(current_device=None)


class _Pages:
    def __init__(self):
        self.index = 0

    def setCurrentIndex(self, i):
        self.index = i


class _Window:
    def __init__(self):
        self.device_manager = _DeviceManager()
        self.settings = _Settings()
        self.ios_pages = _Pages()
        self.selected = None

    def autosave_enabled(self):
        return True

    def open_presets_section(self):
        pass

    def change_selected_device(self, index):
        self.selected = index

    def refresh_devices(self):
        pass


print("\nWave 11 visual baseline")
colors = ColorThemeManager.instance().colors
# v4 restoration (user order 2026-10-03): the shipped palette is the v4
# SKY palette again — soft blue-white body, white rail, Apple-blue brand.
check("content surface is the v4 sky body", colors.bg_primary == "#F2F7FF",
      colors.bg_primary)
check("rail surface is v4 white", colors.menu_bg == "#FFFFFF", colors.menu_bg)
check("brand blue is the v4 Apple blue", colors.brand == "#007AFF",
      colors.brand)
check("background floaters use the soft v4 tints",
      set(FLOAT_TINTS) == {"#BFD9FA", "#A9CBF7", "#C9DFFB", "#9DC2F2",
                           "#D4E4FC"},
      str(FLOAT_TINTS))
for key in ("global", "modern_card", "sidebar_nav_button", "nav_bar"):
    check(f"style resolves: {key}", bool(t(key).strip()))
check("app version is exactly 11.0", App_Version == "11.0", App_Version)
check("app build adds no release label", App_Build == 0, str(App_Build))

print("\nWorkSlop v4 sidebar (main UI)")
sidebar = WorkSlopSidebar()
check("sidebar width is the v4 rail", sidebar.width() == SIDEBAR_WIDTH == 216,
      str(sidebar.width()))
check("sidebar is the v4 WorkSlop menu set",
      [(menu_id, label) for menu_id, label, _icon in MENUS] == [
          ("home", "Home"), ("tweaks", "Tweaks"),
          ("gestalt", "MobileGestalt"), ("wallpaper", "Wallpaper"),
          ("backup", "Backup"), ("appdata", "App Data"),
          ("themes", "Themes"), ("settings", "Settings")],
      str(MENUS))
check("sidebar version label is clean 11.0",
      sidebar._version_lbl.text() == "WorkSlop Desktop v11.0",
      sidebar._version_lbl.text())
sidebar.select("tweaks")
check("sidebar select checks Tweaks", sidebar._buttons["tweaks"][0].isChecked())
sidebar.set_gestalt_locked(True, "locked for test")
check("sidebar MobileGestalt lock works",
      not sidebar._buttons["gestalt"][0].isEnabled())
sidebar.set_gestalt_locked(False)
check("sidebar MobileGestalt unlock works",
      sidebar._buttons["gestalt"][0].isEnabled())
sidebar.set_menu_enabled("settings", False)
check("sidebar menu enable API works",
      not sidebar._buttons["settings"][0].isEnabled())
sidebar.close()

print("\ndual-interface ThemeManager")
_qs = QSettings("WorkSlop", "WorkSlop")
_qs.remove("ui/theme")
_qs.sync()
tm = ThemeManager(None)
check("fresh install defaults to WorkSlop UI",
      tm.current_theme == ThemeManager.IOS, str(tm.current_theme))
tm.save_theme(ThemeManager.CLASSIC)
check("classic persists and reloads",
      ThemeManager(None).current_theme == ThemeManager.CLASSIC)
tm.save_theme(ThemeManager.FULL_NUGGET)
check("full nugget persists and reloads",
      ThemeManager(None).current_theme == ThemeManager.FULL_NUGGET)
_qs.setValue("ui/theme", "classic")
_qs.sync()
check("legacy 'classic' setting still means the WorkSlop-icon Nugget UI",
      ThemeManager(None).current_theme == ThemeManager.CLASSIC)
_qs.setValue("ui/theme", "nonsense")
_qs.sync()
check("unknown setting falls back to WorkSlop UI (no trap)",
      ThemeManager(None).current_theme == ThemeManager.IOS)
_qs.remove("ui/theme")
_qs.sync()
tm.save_theme(ThemeManager.IOS)
check("WorkSlop persists and reloads",
      ThemeManager(None).current_theme == ThemeManager.IOS)

print("\nfirst-launch interface picker")
picker = InterfacePickerDialog()
picker_text = " ".join(w.text() for w in picker.findChildren(QLabel))
check("picker offers WorkSlop as the main UI", "WorkSlop" in picker_text,
      picker_text)
check("picker offers Nugget as the second UI", "Nugget" in picker_text,
      picker_text)
check("picker says Nugget uses WorkSlop icons",
      "WorkSlop icons" in picker_text, picker_text)
check("picker offers Full Nugget as the third UI",
      "Full Nugget" in picker_text
      and "original Nugget interface" in picker_text, picker_text)
picker._pick("classic")
check("picker records the Nugget choice", picker.choice == "classic")
picker._pick("full_nugget")
check("picker records the Full Nugget choice",
      picker.choice == "full_nugget")
picker.close()

print("\nclassic Nugget chrome uses the WorkSlop icon set")
expected_classic_icons = {
    "phoneIconBtn": ":/icon/ws-device.svg",
    "refreshBtn": ":/icon/ws-refresh.svg",
    "homePageBtn": ":/icon/ws-device.svg",
    "gestaltPageBtn": ":/icon/ws-chip.svg",
    "euEnablerPageBtn": ":/icon/ws-flash.svg",
    "statusBarPageBtn": ":/icon/ws-signal.svg",
    "passcodePageBtn": ":/icon/ws-toolbox.svg",
    "springboardOptionsPageBtn": ":/icon/ws-apps.svg",
    "internalOptionsPageBtn": ":/icon/ws-sliders.svg",
    "liquidGlassPageBtn": ":/icon/ws-glass.svg",
    "daemonsPageBtn": ":/icon/ws-sliders.svg",
    "iconThemesPageBtn": ":/icon/ws-wallpaper.svg",
    "applyPageBtn": ":/icon/ws-backup.svg",
    "posterboardPageBtn": ":/icon/ws-poster.svg",
    "settingsPageBtn": ":/icon/ws-gear.svg",
}
for widget_name, resource in expected_classic_icons.items():
    check(f"classic icon {widget_name}",
          _HIDDEN_THEMED_ICONS.get(widget_name) == resource
          and QFile(resource).exists(),
          str(_HIDDEN_THEMED_ICONS.get(widget_name)))
check("classic brand/social glyphs stay truthful",
      _HIDDEN_THEMED_ICONS["mainDevBtn"] == ":/icon/github.svg"
      and _HIDDEN_THEMED_ICONS["discordBtn"] == ":/icon/discord.svg")

print("\nanimated background")
sky = SkyBackground()
check("floater count", len(sky._floaters) == FLOAT_COUNT,
      str(len(sky._floaters)))
sky.resize(1000, 600)
sky.show()
sky.start()
check("timer animating", sky._timer.isActive())
app.processEvents()
before = [(f.rx, f.ry) for f in sky._floaters]
for _ in range(4):
    sky._tick()
after = [(f.rx, f.ry) for f in sky._floaters]
check("floaters move", before != after)
sky.hide()
sky.stop()
sky.close()

print("\ndevice-matched screen cutout (PosterBoard preview)")
_NOTCH_CASES = [
    ("iPhone12,1", "notch_large"),
    ("iPhone12,5", "notch_large"),
    ("iPhone13,2", "notch_large"),
    ("iPhone13,4", "notch_large"),
    ("iPhone14,2", "notch_small"),
    ("iPhone14,5", "notch_small"),
    ("iPhone14,6", "notch_small"),
    ("iPhone14,7", "notch_small"),
    ("iPhone14,8", "notch_small"),
    ("iPhone15,2", "island"),
    ("iPhone15,3", "island"),
    ("iPhone15,4", "island"),
    ("iPhone15,5", "island"),
    ("iPhone16,1", "island"),
    ("iPhone16,2", "island"),
    ("iPhone17,1", "island"),
    ("iPhone17,3", "island"),
    ("iPhone18,1", "island"),
    ("iPhone18,3", "island"),
    ("", "island"),
    (None, "island"),
    ("iPad13,1", "island"),
    ("garbage", "island"),
]
for product, expected in _NOTCH_CASES:
    check(f"cutout {product!r} -> {expected}",
          notch_type_for_product(product) == expected,
          notch_type_for_product(product))
pf = PhoneFrame()
check("frame defaults to Dynamic Island", pf.notch_type == "island")
pf.set_product_type("iPhone13,2")
check("frame follows iPhone 12 (large notch)", pf.notch_type == "notch_large")
pf.set_product_type("iPhone14,5")
check("frame follows iPhone 13 (small notch)", pf.notch_type == "notch_small")
pf.set_product_type("iPhone15,2")
check("frame follows 14 Pro (island)", pf.notch_type == "island")
check("frame starts on lock screen", not pf.showing_home_screen)
pf.show_home_screen()
check("show_home_screen lands on home screen", pf.showing_home_screen)
check("home grid is a full labelled app grid", len(_HOME_GRID_APPS) == 20,
      str(len(_HOME_GRID_APPS)))
check("dock holds the four classic apps",
      [label for label, _k in _DOCK_APPS] ==
      ["Phone", "Safari", "Messages", "Music"])
pf.close()

print("\nHome is the restored v4 page (hero + 9 feature tiles)")
window = _Window()
home = IOSHomePage(window)
app.processEvents()
check("Home shows the big Apple brand logo (no phone frame)",
      not home._hero_logo.pixmap().isNull())
check("Home has no phone frame widget", not hasattr(home, "_phone"))
check("hero title is WorkSlop", home._title.text() == "WorkSlop",
      home._title.text())
check("device picker shows the device",
      home.device_combo.itemText(0) == "iPhone 14 (@ USB)",
      home.device_combo.itemText(0))
check("device subtitle shows version and build",
      home.subtitle.text() == "iPhone (iOS 26.6.1 23G83)",
      home.subtitle.text())
check("status reads Supported with a supported device",
      "Supported!" in home.status_lbl.text(), home.status_lbl.text())
check("all nine v4 feature tiles exist",
      [title.text() for _icon, _res, title, _sub in home._tiles] == [
          "Tweaks", "Liquid Glass", "App Data", "MobileGestalt",
          "PosterBoard", "Daemons", "Status Bar", "Custom Icon",
          "Passcode Theme"],
      str([title.text() for _icon, _res, title, _sub in home._tiles]))
check("no UNPROVEN / device-test text on any tile",
      all("UNPROVEN" not in title.text() and "device test" not in title.text()
          and "UNPROVEN" not in sub.text() and "device test" not in sub.text()
          for _icon, _res, title, sub in home._tiles))
home._on_tile_clicked(home.tweaks_card, 1)
check("tile click navigates the iOS page stack",
      window.ios_pages.index == 1, str(window.ios_pages.index))
home.set_mobilegestalt_locked(True, "26.6.1")
check("MobileGestalt tile locks with an explanation",
      home.mobilegestalt_card in home._tile_locks
      and home.mobilegestalt_card.graphicsEffect() is not None)
home.set_mobilegestalt_locked(False)
check("MobileGestalt tile unlocks",
      home.mobilegestalt_card not in home._tile_locks
      and home.mobilegestalt_card.graphicsEffect() is None)
check("preset widget rides the v4 home", home.preset_widget is not None)
check("process status starts hidden", home.process_status_lbl.isHidden())
home.close()

print("\nAbout carries the English Nugget UI reference")
about = AboutProgramDialog()
about_texts = ([w.text() for w in about.findChildren(QLabel)]
               + [w.text() for w in about.findChildren(QToolButton)])
# User order 2026-10-03: the "UI reference: 3uTools" credit is removed
# entirely and replaced by the English Nugget UI reference.
check("About has no 3uTools credit anywhere",
      not any("3uTools" in text for text in about_texts),
      str([text for text in about_texts if "3u" in text]))
check("About carries the Nugget UI reference",
      any("UI reference: Nugget UI" in text for text in about_texts),
      str([text for text in about_texts if "reference" in text]))
check("About states the second interface is based on the Nugget UI",
      any("second interface based on the Nugget UI" in text
          for text in about_texts))
check("About names WorkSlop Desktop",
      any("WorkSlop Desktop" in text for text in about_texts))
about.close()

print("\nfullscreen behaviour")


class _FullscreenHarness(NavigationMixin, QMainWindow):
    pass


harness = _FullscreenHarness()
harness.resize(1000, 600)
harness.show()
app.processEvents()
check("starts windowed", not harness.isFullScreen())
check("toggle enters fullscreen",
      harness.toggle_fullscreen() and harness.isFullScreen())
app.processEvents()
check("toggle leaves fullscreen",
      not harness.toggle_fullscreen() and not harness.isFullScreen())
f11 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F11,
                Qt.KeyboardModifier.NoModifier)
check("F11 handled", harness.eventFilter(harness, f11) is True)
check("F11 enters fullscreen", harness.isFullScreen())
esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                Qt.KeyboardModifier.NoModifier)
check("ESC leaves fullscreen first",
      harness.eventFilter(harness, esc) is True and not harness.isFullScreen())
harness._install_fullscreen_shortcuts()
check("fullscreen shortcuts installed",
      len(getattr(harness, "_fullscreen_shortcuts", ())) == 2)
_f11_sc, _esc_sc = harness._fullscreen_shortcuts
_f11_sc.activated.emit()
check("F11 shortcut enters fullscreen", harness.isFullScreen())
_esc_sc.activated.emit()
check("ESC shortcut leaves fullscreen", not harness.isFullScreen())
harness.close()

print("\nreal MainWindow: WorkSlop main UI + Nugget second UI (subprocess)")
# The real window owns device-detection worker threads that can outlive
# the checks and stall interpreter shutdown, so the dual-shell drive
# runs in a child process that reports each check and hard-exits.
_CHILD = r'''
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

P = 0


def check(name, cond, extra=""):
    global P
    assert cond, f"FAILED: {name} {extra}"
    P += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""), flush=True)


from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication

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
import src.qt.resources_rc  # noqa: F401
from src.controllers.settings import Settings
from src.controllers.translator import Translator
from src.devicemanagement.device_manager import DeviceManager
from src.gui.ios.theme_manager import ThemeManager
from src.gui.main_window import MainWindow

qs = QSettings("WorkSlop", "WorkSlop")
qs.setValue("ui/theme", "ios")
qs.sync()
win = MainWindow(device_manager=DeviceManager(),
                 translator=Translator(app, Settings()))
app.processEvents()
check("main window starts in WorkSlop UI",
      win.theme_manager.current_theme == ThemeManager.IOS)
check("WorkSlop rail visible / generated Nugget rail hidden",
      not win.workslop_sidebar.isHidden() and win.ui.sidebar.isHidden())
check("device bar is shared by both shells", not win.ui.deviceBar.isHidden())
check("WorkSlop shell starts on iOS-style Home",
      win.content_stack.currentIndex() == 1
      and win.ios_pages.currentIndex() == 0)
check("modern shell is not instantiated",
      not hasattr(win, "workslop_topbar")
      and not hasattr(win, "workslop_footer")
      and not hasattr(win, "device_panel"))
check("window version label is branded and clean",
      "WorkSlop" in win.ui.appVersionLbl.text()
      and "11.0" in win.ui.appVersionLbl.text()
      and "GoldenNugget" not in win.ui.appVersionLbl.text()
      and "pre-release" not in win.ui.appVersionLbl.text().lower()
      and "beta" not in win.ui.appVersionLbl.text().lower()
      and "stable" not in win.ui.appVersionLbl.text().lower(),
      win.ui.appVersionLbl.text())

win._on_workslop_menu("tweaks")
check("WorkSlop Tweaks menu opens the tweak stack",
      win.ios_pages.currentIndex() == 1
      and win.workslop_sidebar._buttons["tweaks"][0].isChecked())
win.show_ios_page(9)  # Liquid Glass section page
check("Liquid Glass section highlights the v4 Tweaks rail item",
      win.workslop_sidebar._buttons["tweaks"][0].isChecked())
check("Nugget Liquid Glass set is hidden in the WorkSlop UI",
      win.ios_liquidglass.content._nugget_lg_box is not None
      and win.ios_liquidglass.content._nugget_lg_box.isHidden())
win._on_workslop_menu("wallpaper")
check("WorkSlop Wallpaper menu opens PosterBoard",
      win.ios_pages.currentIndex() == 2
      and win.workslop_sidebar._buttons["wallpaper"][0].isChecked())
check("Settings picker starts on WorkSlop",
      win.ios_settings.interface_buttons[ThemeManager.IOS].isChecked())

# Flip through the real Settings picker, exactly as a user would.
win.ios_settings.interface_buttons[ThemeManager.CLASSIC].click()
app.processEvents()
check("Settings picker selects Nugget UI",
      win.theme_manager.current_theme == ThemeManager.CLASSIC)
check("Nugget rail visible / WorkSlop rail hidden",
      not win.ui.sidebar.isHidden() and win.workslop_sidebar.isHidden())
win.ios_settings.refresh()
check("Settings picker reflects Nugget after refresh",
      win.ios_settings.interface_buttons[ThemeManager.CLASSIC].isChecked())
def _icon_hash(btn):
    from PySide6.QtCore import QBuffer, QIODevice
    import hashlib
    pm = btn.icon().pixmap(24, 24)
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")
    return hashlib.sha256(bytes(buf.data())).hexdigest()
ws_icon_hash = _icon_hash(win.ui.liquidGlassPageBtn)
win.show_home()
check("Nugget Home is classic stack page 0",
      win.content_stack.currentIndex() == 0
      and win.ui.homePageBtn.isChecked())
win.on_daemonsPageBtn_clicked()
app.processEvents()
check("Nugget Daemons is classic stack page 2",
      win.content_stack.currentIndex() == 2
      and win.ui.daemonsPageBtn.isChecked())
win.show_ios_page(10)  # Icon Themes needs the shared header action.
check("hosted Icon Themes keeps its shared header in Nugget UI",
      win.content_stack.currentIndex() == 1
      and win.ios_pages.currentIndex() == 10
      and not win.ios_nav.isHidden()
      and win.ui.iconThemesPageBtn.isChecked())
win.show_ios_page(4)  # Settings does not need that header in Nugget UI.
check("hosted Settings hides the shared header in Nugget UI",
      win.content_stack.currentIndex() == 1
      and win.ios_pages.currentIndex() == 4
      and win.ios_nav.isHidden()
      and win.ui.settingsPageBtn.isChecked())

# Third UI: Full Nugget (original icons + dark chrome), same shell.
win.ios_settings.interface_buttons[ThemeManager.FULL_NUGGET].click()
app.processEvents()
check("Settings picker selects Full Nugget UI",
      win.theme_manager.current_theme == ThemeManager.FULL_NUGGET)
check("Full Nugget keeps the classic shell",
      not win.ui.sidebar.isHidden() and win.workslop_sidebar.isHidden())
check("Full Nugget sidebar icons are the originals, not the WorkSlop set",
      _icon_hash(win.ui.liquidGlassPageBtn) != ws_icon_hash)
win.show_ios_page(9)
app.processEvents()
check("Nugget Liquid Glass set is visible in Full Nugget",
      win.ios_liquidglass.content._nugget_lg_box is not None
      and not win.ios_liquidglass.content._nugget_lg_box.isHidden())
win.ios_settings.interface_buttons[ThemeManager.CLASSIC].click()
app.processEvents()
win.show_ios_page(9)
app.processEvents()
check("Nugget Liquid Glass set is visible in Nugget UI too",
      not win.ios_liquidglass.content._nugget_lg_box.isHidden())
check("Nugget UI icons are back to the WorkSlop set",
      _icon_hash(win.ui.liquidGlassPageBtn) == ws_icon_hash)

win.ios_settings.interface_buttons[ThemeManager.IOS].click()
app.processEvents()
win.show_home()
check("switching back restores WorkSlop Home",
      win.theme_manager.current_theme == ThemeManager.IOS
      and win.content_stack.currentIndex() == 1
      and win.ios_pages.currentIndex() == 0
      and not win.workslop_sidebar.isHidden()
      and win.ui.sidebar.isHidden()
      and win.workslop_sidebar._buttons["home"][0].isChecked())
win.close()
print(f"MAINWINDOW-DUAL-OK {P}", flush=True)
os._exit(0)
'''

import subprocess  # noqa: E402

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_child_env = dict(os.environ, PYTHONUNBUFFERED="1")
_proc = subprocess.run(
    [sys.executable, "-c", _CHILD], cwd=_repo_root, env=_child_env,
    capture_output=True, text=True, timeout=240)
for _line in _proc.stdout.splitlines():
    print(_line)
if _proc.stderr.strip():
    print(_proc.stderr[-2000:])
check("dual-shell MainWindow subprocess passed",
      _proc.returncode == 0 and "MAINWINDOW-DUAL-OK" in _proc.stdout,
      f"rc={_proc.returncode}")
_child_pass = int(_proc.stdout.rsplit("MAINWINDOW-DUAL-OK", 1)[1].split()[0]) \
    if "MAINWINDOW-DUAL-OK" in _proc.stdout else 0
PASS += _child_pass

print(f"\nALL {PASS} CHECKS PASSED")
