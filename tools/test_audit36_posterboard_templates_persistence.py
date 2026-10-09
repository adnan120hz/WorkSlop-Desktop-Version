#!/usr/bin/env python3
"""Fix Audit 36: PosterBoard/Templates choices persist across restarts.

Before: PresetManager._serialize() excluded TweakID.PosterBoard outright,
so the selected tendies/templates/video wallpaper, the delivery mode and
the saved configuration IDs all died on restart; template imports never
fired the tweak-change channel either, so AutoSave never picked them up.
The tendie thumbnail lookup also failed silently (missing/corrupt preview
-> empty card) and Clear Saved IDs only mutated memory.

Fix pinned here (one preset path, no parallel store):
* PosterBoard + Templates state round-trips through PresetManager
  save -> load with a fresh manager instance;
* a missing/corrupt thumbnail renders a visible placeholder;
* Clear Saved IDs writes through PreferenceManager immediately.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit36_posterboard_templates_persistence.py
"""
import json
import os
import sys
import tempfile
import zipfile
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QListWidget  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)

from src.controllers.preset_manager import PresetManager  # noqa: E402
from src.tweaks.tweak_names import TweakID  # noqa: E402
from src.tweaks.tweaks import tweaks  # noqa: E402
from src.tweaks.posterboard.pb_config_item import PBConfigItem  # noqa: E402

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def make_manager(tmpdir):
    pm = PresetManager()
    pm.presets_dir = tmpdir
    return pm


def make_tendie(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("descriptor/test/versions/0/contents/x.txt", "hi")
    return path


def make_batter(path):
    config = {
        "title": "Audit36 Template", "author": "Tester",
        "domain": "com.apple.PosterBoard", "format_version": 2,
        "options": [],
    }
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("config.json", json.dumps(config))
        z.writestr("descriptor/test/versions/0/contents/x.txt", "hi")
    return path


# =============================================================================
def test_round_trip(tmpdir):
    print("\nround-trip: PosterBoard + Templates survive save -> fresh load")
    tendie = make_tendie(os.path.join(tmpdir, "wp.tendies"))
    batter = make_batter(os.path.join(tmpdir, "tpl.batter"))
    thumb = os.path.join(tmpdir, "thumb.heic")
    video = os.path.join(tmpdir, "video.mov")
    with open(thumb, "wb") as f:
        f.write(b"thumb")
    with open(video, "wb") as f:
        f.write(b"video")

    pb = tweaks[TweakID.PosterBoard]
    pb.tendies = []
    check("tendie added", pb.add_tendie(tendie) is True)
    pb.videoThumbnail = thumb
    pb.videoFile = video
    pb.loop_video = False
    pb.reverse_video = True
    pb.use_foreground = True
    pb.use_configs = True
    pb.calculationMode = "discrete"
    pb.config_manager.saved_items = [
        PBConfigItem("UUID-1", "com.apple.WallpaperKit.CollectionsPoster",
                     set_selected=True)]

    tt = tweaks[TweakID.Templates]
    tt.templates = []
    tt.add_template(batter)
    check("template added", len(tt.templates) == 1)

    pm = make_manager(tmpdir)
    check("save succeeds", pm.save_preset("Audit36") is True)
    with open(pm.get_preset_path("Audit36"), encoding="utf-8") as f:
        saved = json.load(f)
    pb_data = saved.get("tweaks", {}).get("PosterBoard", {})
    check("preset file contains PosterBoard", bool(pb_data))
    check("tendies stored as paths", pb_data.get("tendies") == [tendie],
          str(pb_data.get("tendies")))
    check("video selection stored",
          pb_data.get("video_file") == video
          and pb_data.get("video_thumbnail") == thumb)
    check("mode/options stored",
          pb_data.get("use_configs") is True
          and pb_data.get("loop_video") is False
          and pb_data.get("calculation_mode") == "discrete")
    check("saved config IDs stored",
          (pb_data.get("saved_config_ids") or [{}])[0].get("uuid") == "UUID-1")
    tpl_data = saved.get("tweaks", {}).get("Templates", {})
    check("template paths stored", tpl_data.get("templates") == [batter],
          str(tpl_data.get("templates")))

    # Simulate an app restart: fresh manager, tweak state back to defaults.
    pb.tendies = []
    pb.videoThumbnail = None
    pb.videoFile = None
    pb.loop_video = True
    pb.reverse_video = False
    pb.use_foreground = False
    pb.use_configs = False
    pb.calculationMode = "linear"
    pb.config_manager.saved_items = []
    tt.templates = []

    pm2 = make_manager(tmpdir)
    check("fresh load succeeds", pm2.load_preset("Audit36") is True)
    check("tendies restored", [t.path for t in pb.tendies] == [tendie])
    check("video selection restored",
          pb.videoFile == video and pb.videoThumbnail == thumb)
    check("mode/options restored",
          pb.use_configs is True and pb.loop_video is False
          and pb.reverse_video is True and pb.use_foreground is True
          and pb.calculationMode == "discrete")
    ids = pb.config_manager.saved_items
    check("saved config IDs restored",
          len(ids) == 1 and ids[0].uuid == "UUID-1"
          and ids[0].set_selected is True)
    check("templates restored", [t.path for t in tt.templates] == [batter])

    # A tendie whose file vanished is skipped, not restored as a dead path.
    pb.tendies = []
    tt.templates = []
    os.remove(tendie)
    check("reload with missing tendie still succeeds",
          pm2.load_preset("Audit36") is True)
    check("missing tendie skipped", pb.tendies == [])


# =============================================================================
def test_thumbnail_placeholder(tmpdir):
    print("\nthumbnail lookup: missing/corrupt -> placeholder, never silent")
    import src.gui.ios.posterboard as pb_mod
    from PySide6.QtGui import QImage
    from PySide6.QtCore import Qt

    page = pb_mod.IOSPosterboardPage.__new__(pb_mod.IOSPosterboardPage)

    label = QLabel()
    page._set_tendie_thumbnail(label, os.path.join(tmpdir, "gone.png"))
    check("missing file -> placeholder text shown",
          label.text() == "No Preview" and label.pixmap().isNull(),
          repr(label.text()))

    corrupt = os.path.join(tmpdir, "corrupt.png")
    with open(corrupt, "wb") as f:
        f.write(b"this is not an image")
    label2 = QLabel()
    page._set_tendie_thumbnail(label2, corrupt)
    check("corrupt file -> placeholder text shown",
          label2.text() == "No Preview" and label2.pixmap().isNull(),
          repr(label2.text()))

    good = os.path.join(tmpdir, "good.png")
    img = QImage(120, 90, QImage.Format_RGB32)
    img.fill(Qt.GlobalColor.darkCyan)
    assert img.save(good)
    label3 = QLabel()
    page._set_tendie_thumbnail(label3, good)
    check("valid file -> real 80x80 pixmap, no placeholder",
          not label3.pixmap().isNull() and label3.text() == "")


# =============================================================================
def test_clear_persists_immediately():
    print("\nClear Saved IDs: written to storage at once")
    import src.gui.ios.posterboard as pb_mod
    from src.devicemanagement.preference_manager import PreferenceManager

    pb = tweaks[TweakID.PosterBoard]
    pb.config_manager.saved_items = [PBConfigItem("UUID-9", "ext")]

    page = pb_mod.IOSPosterboardPage.__new__(pb_mod.IOSPosterboardPage)
    page.window = SimpleNamespace(device_manager=SimpleNamespace(
        get_current_device_udid=lambda: "UDID-AUDIT36"))
    page.saved_ids_list = QListWidget()
    page._refresh_saved_ids()

    class FakeBox:
        class StandardButton:
            Yes = 1
            Cancel = 2

        @classmethod
        def question(cls, *a, **kw):
            return cls.StandardButton.Yes

    saved_calls = []
    synced = []
    real_box = pb_mod.QMessageBox
    real_save = PreferenceManager.save_pbconfig_ids
    real_prefs = PreferenceManager.get_pbconfigs_prefs
    pb_mod.QMessageBox = FakeBox
    PreferenceManager.save_pbconfig_ids = staticmethod(
        lambda ids, udid: saved_calls.append((list(ids), udid)))
    PreferenceManager.get_pbconfigs_prefs = staticmethod(
        lambda: SimpleNamespace(sync=lambda: synced.append(True)))
    try:
        page._on_clear_saved_ids()
    finally:
        pb_mod.QMessageBox = real_box
        PreferenceManager.save_pbconfig_ids = real_save
        PreferenceManager.get_pbconfigs_prefs = real_prefs

    check("saved IDs cleared in memory",
          pb.config_manager.saved_items == [])
    check("clear persisted immediately for the current device",
          saved_calls == [([], "UDID-AUDIT36")], str(saved_calls))
    check("preference store synced at once", synced == [True])


def main():
    tmpdir = tempfile.mkdtemp(prefix="audit36-")
    test_round_trip(tmpdir)
    test_thumbnail_placeholder(tmpdir)
    test_clear_persists_immediately()
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
