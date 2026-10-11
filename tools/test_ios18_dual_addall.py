"""Offscreen proof for the iOS 18 Add All tables (user order 2026-10-09,
extended 2026-10-11 with the Tinted table; the Rounded tables were
removed by explicit user order 2026-10-11, revision).

Run from repo root with QT_QPA_PLATFORM=offscreen.
Proves: three tables exist with exact button names; Add All Dark adds
exactly the 50 dark-artwork apps (Shortcuts has no Dark asset and is
skipped); Add All Light then adds only the still-missing Shortcuts
(Light); a second Add All adds nothing; Add All Tinted adds the 51
tinted assets with byte identity; every stored theme's icon path
matches the variant chosen.
"""
import hashlib
import os
import sys


def sha256_of(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication

app = QApplication([])

from src.tweaks.tweaks import tweaks, TweakID
from src.gui.ios.icon_themes import IOSIconThemesPage, IOS18_ICONS

page = IOSIconThemesPage(None)
tweak = tweaks[TweakID.IconThemes]

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok   {name}")
    else:
        failed += 1
        print(f"  FAIL {name} {extra}")


# Structure: three tables (Light, Dark, Tinted),
# three add-all buttons, exact object names, 51 rows each.
check("three tables built", len(page._ios18_tables) == 3)
check("three add-all buttons", len(page._ios18_add_all_buttons) == 3)
names = {b.objectName() for b in page._ios18_add_all_buttons}
check("add-all object names", names == {
    "ios18AddAllLight", "ios18AddAllDark",
    "ios18AddAllTinted"}, str(names))
check("row counts 51/51/51",
      [t.rowCount() for t in page._ios18_tables] == [51, 51, 51])
labels = [t.horizontalHeaderItem(0).text() for t in page._ios18_tables]
check("table header labels", labels == [
    "Light", "Dark", "Tinted"], str(labels))

tweak.themes = []

# 1) Add All Dark first: exactly 50 (every app except Shortcuts).
# store_icon copies the PNG into the persistent store and repoints
# icon_path there, so correctness is proven by byte identity with the
# source asset (checked via the page's own icon_asset_path).
from src.gui.ios.icon_themes import icon_asset_path

slug_by_bundle = {b: s for _n, b, s in IOS18_ICONS}
page._use_all_icons(dark=True)
check("dark added 50", len(tweak.themes) == 50, f"got {len(tweak.themes)}")
check("stored bytes == Dark assets", all(
    sha256_of(t.icon_path) == sha256_of(icon_asset_path(slug_by_bundle[t.bundle_id], True))
    for t in tweak.themes))
check("shortcuts absent after dark", all(t.bundle_id != "com.apple.shortcuts" for t in tweak.themes))
check("status mentions Dark", "(Dark)" in page._ios18_status.text(), page._ios18_status.text())

# 2) Add All Light: only Shortcuts is new -> exactly 1 more, Light path.
page._use_all_icons(dark=False)
check("light then adds exactly 1", len(tweak.themes) == 51, f"got {len(tweak.themes)}")
new = [t for t in tweak.themes if t.bundle_id == "com.apple.shortcuts"]
check("the 1 is Shortcuts Light", len(new) == 1
      and sha256_of(new[0].icon_path) == sha256_of(icon_asset_path("shortcuts", False)))

# 3) Both again: nothing new.
page._use_all_icons(dark=True)
page._use_all_icons(dark=False)
check("re-run adds nothing", len(tweak.themes) == 51, f"got {len(tweak.themes)}")
check("status already-present", "already in Icon" in page._ios18_status.text(), page._ios18_status.text())

# 4) Fresh state: Add All Light adds all 51.
tweak.themes = []
page._use_all_icons(dark=False)
check("light-first adds 51", len(tweak.themes) == 51, f"got {len(tweak.themes)}")
check("stored bytes == Light assets", all(
    sha256_of(t.icon_path) == sha256_of(icon_asset_path(slug_by_bundle[t.bundle_id], False))
    for t in tweak.themes))

# 5) Fresh state: Add All Tinted adds all 51 tinted assets.
tweak.themes = []
page._use_all_icons(dark=False, tinted=True)
check("tinted adds 51", len(tweak.themes) == 51, f"got {len(tweak.themes)}")
check("stored bytes == Tinted assets", all(
    sha256_of(t.icon_path) == sha256_of(icon_asset_path(slug_by_bundle[t.bundle_id], False, True))
    for t in tweak.themes))
check("status mentions Tinted",
      "(Tinted)" in page._ios18_status.text(), page._ios18_status.text())

# 6) Tinted table shows the tinted artwork in its thumbnails.
pix = page._pixmap("camera", False, True)
check("tinted thumbnail loads", not pix.isNull())
pix2 = page._pixmap("camera", False, False)
check("plain thumbnail differs from tinted",
      pix.toImage() != pix2.toImage())

tweak.themes = []
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
