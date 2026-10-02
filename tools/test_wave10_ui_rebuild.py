#!/usr/bin/env python3
"""Offscreen checks + screenshots for the modern blue Wave 10 UI.

Contract: bright-blue top bar with five centered category tabs, white left
sidebar with device dropdown + menu, big Apple brand logo on Home (no phone
frame in any state), right info/capacity cards, strong-blue bottom tiles,
light footer, and an animated blue Apple-logo background behind content.
The notch mapping unit checks below still cover PhoneFrame itself, which
remains in use by the PosterBoard tendie preview dialog.

Run: QT_QPA_PLATFORM=offscreen /tmp/sbvenv/bin/python \
    tools/test_wave10_ui_rebuild.py
"""
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


try:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import (
        QApplication, QHBoxLayout, QLabel, QPushButton, QMainWindow,
        QStackedLayout, QVBoxLayout, QWidget)
except Exception as e:
    print(f"skipped: {type(e).__name__}: {e}")
    raise SystemExit(0)

app = QApplication([])
app.setApplicationName("WorkSlop Desktop")

try:
    import src.qt.resources_rc  # noqa: F401
except Exception:
    pass

from src.gui.ios.device_panel import NAV_ITEMS, PANEL_WIDTH, WorkSlopDevicePanel
from src.gui.ios.home import IOSHomePage
from src.gui.ios.phone_frame import (
    PhoneFrame, notch_type_for_product, _DOCK_APPS, _HOME_GRID_APPS)
from src.gui.ios.sky_bg import FLOAT_COUNT, FLOAT_TINTS, SkyBackground
from src.gui.ios.top_bar import HEADER_HEIGHT, TABS, WorkSlopTopBar
from src.gui.main_window_mixins import NavigationMixin
from src.gui.theme import ColorThemeManager, t


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
        return "wave10-offscreen-udid-0001"

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


print("\nmodern blue palette + styles")
colors = ColorThemeManager.instance().colors
check("content is white", colors.bg_primary == "#FFFFFF", colors.bg_primary)
check("brand blue is strong (not pale)", colors.brand == "#0B65D8", colors.brand)
check("menu blue is strong", colors.menu_bg == "#0B65D8", colors.menu_bg)
check("no washed-out float tints", "#7FB8EC" not in FLOAT_TINTS
      and "#5EA9E6" not in FLOAT_TINTS, str(FLOAT_TINTS))
for key in ("device_side_panel", "sidebar_device_header", "sidebar_device_combo",
            "sidebar_nav_button", "info_label", "info_value", "storage_bar",
            "modern_card", "capacity_chip", "phone_link_button",
            "footer_light_text", "footer_light_button", "scroll_area_transparent",
            "nav_bar"):
    check("fluid radii: card 16 / nav pill 18", "border-radius: 16px" in t("modern_card") and "border-radius: 18px" in t("sidebar_nav_button"))
check(f"style resolves: {key}", bool(t(key).strip()))

print("\ntop header bar")
topbar = WorkSlopTopBar()
check("header height", topbar.height() == HEADER_HEIGHT, str(topbar.height()))
check("five reference tabs", [tid for tid, _l, _i, _legacy in TABS] ==
      ["idevice", "apps", "rtwp", "smartflash", "toolbox"])
check("tab labels are WorkSlop destinations",
      [label for _tid, label, _i, _legacy in TABS] ==
      ["Device", "Tweaks", "PosterBoard", "MobileGestalt", "Settings"],
      str([label for _tid, label, _i, _legacy in TABS]))
topbar.select("tweaks")
check("legacy select maps to Tweaks", topbar._buttons["apps"][0].isChecked())
topbar.set_gestalt_locked(True, "locked for test")
check("MobileGestalt lock API works", not topbar._buttons["smartflash"][0].isEnabled())
topbar.set_gestalt_locked(False)
check("logo is WorkSlop", topbar._logo_name.text() == "WorkSlop")
check("WS mark present", topbar._logo_mark.text() == "WS")
check("update shortcut exists", topbar._update_btn is not None)

print("\nleft white sidebar")
window = _Window()
panel = WorkSlopDevicePanel(window)
check("panel width", panel.width() == PANEL_WIDTH == 200, str(panel.width()))
check("no CONNECTED DEVICE header", panel._device_header.isHidden())
check("device dropdown shows device", panel.device_combo.currentText() == "iPhone 14")
check("nav maps real pages", [m for m, _l, _i in NAV_ITEMS] ==
      ["home", "tweaks", "liquidglass", "springboard", "internal", "statusbar",
       "posterboard", "daemons", "gestalt", "settings"])
panel.select("liquidglass")
check("sidebar select works", panel._buttons["liquidglass"][0].isChecked())
panel.set_gestalt_locked(True, "locked for test")
check("sidebar gestalt lock works", not panel._buttons["gestalt"][0].isEnabled())
panel.set_gestalt_locked(False)

print("\nanimated background")
sky = SkyBackground()
check("floater count", len(sky._floaters) == FLOAT_COUNT, str(len(sky._floaters)))
check("timer animating", sky.is_animating())
sky.resize(1000, 600)
sky.show()
app.processEvents()
before = sky.floater_positions()
for _ in range(4):
    sky._tick()
after = sky.floater_positions()
check("floaters move", before != after)
sky.hide()
sky.stop()

print("\ndevice-matched screen cutout (notch / Dynamic Island)")
_NOTCH_CASES = [
    ("iPhone12,1", "notch_large"),   # iPhone 11
    ("iPhone12,5", "notch_large"),   # iPhone 11 Pro Max
    ("iPhone13,2", "notch_large"),   # iPhone 12
    ("iPhone13,4", "notch_large"),   # iPhone 12 Pro Max
    ("iPhone14,2", "notch_small"),   # iPhone 13 Pro
    ("iPhone14,5", "notch_small"),   # iPhone 13
    ("iPhone14,6", "notch_small"),   # iPhone SE (2022)
    ("iPhone14,7", "notch_small"),   # iPhone 14
    ("iPhone14,8", "notch_small"),   # iPhone 14 Plus
    ("iPhone15,2", "island"),        # iPhone 14 Pro
    ("iPhone15,3", "island"),        # iPhone 14 Pro Max
    ("iPhone15,4", "island"),        # iPhone 15
    ("iPhone15,5", "island"),        # iPhone 15 Plus
    ("iPhone16,1", "island"),        # iPhone 15 Pro
    ("iPhone16,2", "island"),        # iPhone 15 Pro Max
    ("iPhone17,1", "island"),        # iPhone 16 Pro
    ("iPhone17,3", "island"),        # iPhone 16
    ("iPhone18,1", "island"),        # iPhone 17 series
    ("iPhone18,3", "island"),
    ("", "island"),                  # no device -> modern fallback
    (None, "island"),
    ("iPad13,1", "island"),          # not an iPhone -> fallback
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

print("\nHome modern reference layout")
home = IOSHomePage(window)
app.processEvents()
check("Home shows the big Apple brand logo (no phone frame)",
      hasattr(home, "_brand_logo") and not home._brand_logo.pixmap().isNull())
check("Home has no phone frame widget anymore",
      not hasattr(home, "_phone"))
check("device title is device", home._device_title.text() == "iPhone 14")
check("phone caption is device", home._phone_caption.text() == "iPhone 14")
check("refresh phone link not hidden", not home._refresh_link.isHidden())
check("no big blue info buttons", home._refresh_info_btn.isHidden()
      and home._details_btn.isHidden())
check("Reboot hidden without handler", home._reboot_link.isHidden())
check("Turn Off hidden without handler", home._turnoff_link.isHidden())
check("title card exists", home._title_card.objectName() == "deviceTitleCard")
check("details card exists", home._details_card.objectName() == "deviceDetailsCard")
check("tweak list card replaces capacity card on Home",
      home._catalogue_card.objectName() == "tweakListCard")
check("no Hard Disk Capacity card on Home",
      not hasattr(home, "_capacity_card"))
check("capacity chip hidden without data", home._capacity_chip.isHidden())
check("battery hidden without data", home._battery_value.isHidden())
check("MobileGestalt row Locked on 23G83 (shared decision)",
      home._info_values["gestalt"].text() == "Locked",
      home._info_values["gestalt"].text())
check("serial row hidden without data",
      home._info_rows["serial"].isHidden())
check("storage row hidden without data",
      home._info_rows["storage"].isHidden())
check("device title", home._device_title.text() == "iPhone 14")
check("model in table", home._info_values["model"].text() == "iPhone14,5")
check("iOS in table", home._info_values["ios"].text() == "26.6.1")
check("build in table", home._info_values["build"].text() == "23G83")
check("connection in table", home._info_values["connection"].text() == "USB")
check("support in table", home._info_values["support"].text() != "—")
check("unknown storage honest", home._info_values["storage"].text() == "—")
entries = {entry["id_name"]: entry for entry in home.tweak_catalogue_entries}
check("catalogue registry-derived", "SBHideSearchAffordance" in entries)
check("FlatIcons exception listed", "FlatIconsEverywhere" in entries)
check("action tiles present",
      set(home._tile_by_title) >= {"Refresh", "Backup / Restore", "Tweaks",
                                   "Liquid Glass", "Status Bar", "PosterBoard",
                                   "Daemons", "MobileGestalt", "Reset Tweaks"})
check("statusbar card is a tile", home.statusbar_card is home._tile_by_title["Status Bar"])
check("gestalt card is a tile", home.mobilegestalt_card is home._tile_by_title["MobileGestalt"])

print("\nabout dialog credits")
from PySide6.QtWidgets import QToolButton as _QToolButton
from src.gui.dialogs.dialogs import AboutProgramDialog
about = AboutProgramDialog()
_about_texts = ([w.text() for w in about.findChildren(QLabel)]
                + [w.text() for w in about.findChildren(_QToolButton)])
check("About credits the UI reference",
      "UI reference:" in _about_texts and "3uTools" in _about_texts,
      str([tx for tx in _about_texts if "3uTools" in tx or "reference" in tx]))
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

print("\nfullscreen via window shortcuts (real-Windows path)")
harness._install_fullscreen_shortcuts()
check("fullscreen shortcuts installed",
      len(getattr(harness, "_fullscreen_shortcuts", ())) == 2)
_f11_sc, _esc_sc = harness._fullscreen_shortcuts
_f11_sc.activated.emit()
check("F11 shortcut enters fullscreen", harness.isFullScreen())
_esc_sc.activated.emit()
check("ESC shortcut leaves fullscreen", not harness.isFullScreen())
harness.close()

print("\ncomposite screenshots (shell-shaped)")
shot_dir = os.path.join(os.path.dirname(__file__), "..", "..", "riset",
                        "wave10", "ui-rebuild-screenshots")
os.makedirs(shot_dir, exist_ok=True)
frame = QMainWindow()
frame.setWindowTitle("WorkSlop Desktop")
frame.resize(1280, 840)
central = QWidget(frame)
central.setStyleSheet("background: transparent;")
stack = QStackedLayout(central)
stack.setContentsMargins(0, 0, 0, 0)
stack.setStackingMode(QStackedLayout.StackAll)
stack.addWidget(sky)
content = QWidget(central)
content.setStyleSheet("background: transparent;")
root = QVBoxLayout(content)
root.setContentsMargins(0, 0, 0, 0)
root.setSpacing(0)
root.addWidget(topbar)
body = QHBoxLayout()
body.setContentsMargins(0, 0, 0, 0)
body.setSpacing(0)
body.addWidget(panel)
body.addWidget(home, 1)
root.addLayout(body, 1)
footer = QWidget(frame)
footer.setFixedHeight(30)
footer.setStyleSheet("background-color: #EDF5FD; border-top: 1px solid #BDD7F2;")
fl = QHBoxLayout(footer)
fl.setContentsMargins(12, 0, 10, 0)
f_lbl = QLabel("1 device(s) connected", footer)
f_lbl.setStyleSheet(t("footer_light_text"))
fl.addWidget(f_lbl)
fl.addStretch(1)
f_ver = QLabel("Version: 10.0", footer)
f_ver.setStyleSheet(t("footer_light_text"))
fl.addWidget(f_ver)
f_feed = QPushButton("Feedback", footer)
f_feed.setStyleSheet(t("footer_light_button"))
fl.addWidget(f_feed)
f_btn = QPushButton("Check Update", footer)
f_btn.setStyleSheet(t("footer_light_button"))
fl.addWidget(f_btn)
root.addWidget(footer)
stack.addWidget(content)
sky.lower()
frame.setCentralWidget(central)
frame.setStyleSheet(t("global"))
frame.show()
app.processEvents()
shot_path = os.path.abspath(
    os.path.join(shot_dir, "home-modern-v7.png"))
pixmap = frame.grab()
check("screenshot rendered", not pixmap.isNull(),
      f"{pixmap.width()}x{pixmap.height()}")
check("screenshot saved",
      pixmap.save(shot_path) and os.path.getsize(shot_path) > 10000, shot_path)
frame.showFullScreen()
app.processEvents()
check("composite enters fullscreen", frame.isFullScreen())
check("fullscreen layout expands without clipping",
      topbar.width() <= frame.width()
      and home._brand_logo.width() <= home.width(),
      f"frame={frame.width()} home={home.width()}")
full_path = os.path.abspath(
    os.path.join(shot_dir, "home-modern-fullscreen-offscreen.png"))
full_pixmap = frame.grab()
check("fullscreen screenshot saved",
      full_pixmap.save(full_path) and os.path.getsize(full_path) > 10000,
      full_path)
frame.showNormal()
frame.close()

print(f"\nALL {PASS} CHECKS PASSED")
print(f"screenshot: {shot_path}")
print(f"screenshot: {full_path}")
