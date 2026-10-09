#!/usr/bin/env python3
"""Fix Audit 18: MobileGestalt picker choices persist across restarts.

Before: PresetManager._serialize_tweak() only knew the plist tweak classes,
so a MobileGestaltPickerTweak (Dynamic Island dropdown, spoof pickers) was
stored as just {"type", "enabled"} — the selected option, the plain
MobileGestalt value (e.g. ModelName) and RdarFix's di_type were all lost,
and the page's picker handler never fired the tweak-change channel, so the
AutoSave preset was never even rewritten.

Fix pinned here (the same single preset serializer as Audit 36 — no
parallel store):
* picker index / MobileGestalt value / RdarFix di_type round-trip through
  PresetManager save -> load with a fresh manager instance;
* the Dynamic Island picker handler notifies the shared tweak-change
  channel so AutoSave actually captures the new choice.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit18_gestalt_picker_persistence.py
"""
import json
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)

from src.controllers.preset_manager import PresetManager  # noqa: E402
from src.tweaks import tweak_loader  # noqa: E402
from src.tweaks.tweak_names import TweakID  # noqa: E402
from src.tweaks.tweaks import tweaks  # noqa: E402
from src.tweaks.tweak_classes import set_tweak_change_callback  # noqa: E402

PASS = 0
SUPPORTED_VERSION = "18.5"  # inside the MobileGestalt supported range


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def make_manager(tmpdir):
    pm = PresetManager()
    pm.presets_dir = tmpdir
    return pm


# =============================================================================
def test_round_trip(tmpdir):
    print("\nround-trip: picker/value/di_type survive save -> fresh load")
    tweak_loader.load_mobilegestalt("", SUPPORTED_VERSION)
    check("gestalt family registered", TweakID.DynamicIsland in tweaks)
    device = SimpleNamespace(model="iPhone13,2", build="", version=SUPPORTED_VERSION)
    tweak_loader.load_rdar_fix(device)
    check("rdar fix registered", TweakID.RdarFix in tweaks)

    di = tweaks[TweakID.DynamicIsland]
    di.set_selected_option(3)  # 2622 (iPhone 16 Pro Dynamic Island)
    mn = tweaks[TweakID.ModelName]
    mn.set_value("Audit18 Phone")
    mn.set_enabled(True)
    rdar = tweaks[TweakID.RdarFix]
    rdar.set_di_type(2796)
    rdar.set_enabled(True)

    pm = make_manager(tmpdir)
    check("save succeeds", pm.save_preset("Audit18") is True)
    with open(pm.get_preset_path("Audit18"), encoding="utf-8") as f:
        saved = json.load(f)
    tw = saved.get("tweaks", {})
    check("picker index stored",
          tw.get("DynamicIsland", {}).get("selected_option") == 3,
          str(tw.get("DynamicIsland")))
    check("gestalt value stored",
          tw.get("ModelName", {}).get("value") == "Audit18 Phone",
          str(tw.get("ModelName")))
    check("rdar di_type stored",
          tw.get("RdarFix", {}).get("di_type") == 2796,
          str(tw.get("RdarFix")))

    # Simulate an app restart: fresh manager, tweak state back to defaults.
    di.set_selected_option(0, is_enabled=False)
    mn.set_value("", toggle_enabled=False)
    mn.set_enabled(False)
    rdar.set_di_type(-1)
    rdar.set_enabled(False)

    pm2 = make_manager(tmpdir)
    check("fresh load succeeds",
          pm2.load_preset("Audit18", device_version=SUPPORTED_VERSION) is True)
    check("picker index restored", di.get_selected_option() == 3,
          str(di.get_selected_option()))
    check("picker tweak re-enabled", di.enabled is True)
    check("gestalt value restored",
          mn.value == "Audit18 Phone" and mn.enabled is True, str(mn.value))
    check("rdar di_type restored",
          rdar.di_type == 2796 and rdar.enabled is True, str(rdar.di_type))
    check("nothing recorded as skipped",
          pm2.last_skipped == [], str(pm2.last_skipped))

    di.set_selected_option(0, is_enabled=False)
    rdar.set_enabled(False)


# =============================================================================
def test_picker_handler_notifies_autosave():
    print("\npicker handler: choosing an option fires the AutoSave channel")
    import src.gui.ios.mobilegestalt as mg_mod

    check("gestalt page uses the shared serializer path (no PresetManager "
          "of its own)", "PresetManager" not in open(
              mg_mod.__file__, encoding="utf-8").read())

    dm = SimpleNamespace(
        data_singleton=SimpleNamespace(
            current_device=SimpleNamespace(build="", version=SUPPORTED_VERSION)),
        get_current_device_model=lambda: "iPhone13,2")
    content = mg_mod._GestaltContent.__new__(mg_mod._GestaltContent)
    content.window = SimpleNamespace(device_manager=dm)
    content._switches = {}

    di = tweaks[TweakID.DynamicIsland]
    di.set_selected_option(0, is_enabled=False)
    fired = []
    set_tweak_change_callback(lambda: fired.append(True))
    try:
        content._on_di_activated(2)  # dropdown row 2 -> option index 1
    finally:
        set_tweak_change_callback(None)
    check("handler applied the picker choice",
          di.get_selected_option() == 1 and di.enabled is True,
          str(di.get_selected_option()))
    check("handler notified the tweak-change (AutoSave) channel",
          len(fired) >= 1, str(len(fired)))
    di.set_selected_option(0, is_enabled=False)


def main():
    tmpdir = tempfile.mkdtemp(prefix="audit18-")
    test_round_trip(tmpdir)
    test_picker_handler_notifies_autosave()
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
