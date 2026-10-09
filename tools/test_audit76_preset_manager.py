#!/usr/bin/env python3
"""Audit 76 (lite): real PresetManager round trip (no Fake).

Audit 76 found that the only preset coverage used a FakePresetManager, so
the real load/save path (PresetManager._serialize -> JSON on disk ->
_apply, with the Fix Audit 43 schema gate in front of both) had no actual
test. This suite drives the REAL src.controllers.preset_manager.PresetManager:

* save a preset from live ``tweaks`` state, read the JSON back off disk
  (schema version and marker value must be in the file),
* reset the live tweak, load the preset again, and require the live
  state to be restored exactly,
* legacy schemas are rejected through the public load path: metadata
  version 1 and a version-less file both fail with the unsupported
  version named in ``PresetManager.last_error`` (Fix Audit 43), and
* list/delete behave over the same real directory.

The manager's presets directory is redirected at a temp folder, so the
suite is hermetic; the live ``tweaks`` dict is restored afterwards.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit76_preset_manager.py
"""
import copy
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)

from src.controllers.preset_manager import (  # noqa: E402
    PRESET_VERSION, PresetManager)
from src.tweaks import tweak_loader  # noqa: E402
from src.tweaks.capabilities import tweak_deliverability  # noqa: E402
from src.tweaks.tweak_classes import BasicPlistTweak  # noqa: E402
from src.tweaks.tweak_names import TweakID  # noqa: E402
from src.tweaks.tweaks import tweaks  # noqa: E402

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def pick_test_tweak():
    """One real, default-deliverable BasicPlistTweak with a plist value."""
    tweak_loader.load_plist_tweaks()
    for tid, tweak in sorted(tweaks.items(), key=lambda kv: kv[0].name):
        if not isinstance(tweak, BasicPlistTweak):
            continue
        if not isinstance(getattr(tweak, "value", None), dict) or not tweak.value:
            continue
        deliverable, _code, _reason = tweak_deliverability(
            tid, device_version="", device_build="", is_iphone=True,
            tweak=tweak)
        if deliverable:
            return tid, tweak
    raise AssertionError("no deliverable BasicPlistTweak available for test")


def main():
    print("\naudit-76-lite: real PresetManager round trip")
    tmp = tempfile.mkdtemp(prefix="workslop-preset-")
    manager = PresetManager()
    # Redirect at a hermetic directory: presets_dir is the single disk
    # anchor every PresetManager path goes through.
    manager.presets_dir = tmp

    tid, tweak = pick_test_tweak()
    print(f"  (driving real tweak {tid.name})")
    marker_key = sorted(tweak.value.keys())[0]
    original_enabled = tweak.enabled
    original_value = copy.deepcopy(tweak.value)
    marker_value = copy.deepcopy(tweak.value)
    marker_value[marker_key] = "WORKSLOP-AUDIT76-MARKER" \
        if isinstance(tweak.value[marker_key], str) else 987654

    try:
        # --- save from live state, and pin what lands on disk ---------
        tweak.set_enabled(True)
        tweak.value = copy.deepcopy(marker_value)
        ok = manager.save_preset(
            "Audit76Real", description="round trip test", tags=["audit"])
        check("save_preset returns True", ok is True)
        path = manager.get_preset_path("Audit76Real")
        check("preset file exists on disk", os.path.isfile(path))
        with open(path, encoding="utf-8") as f:
            on_disk = json.load(f)
        check("on-disk schema version is current",
              on_disk.get("metadata", {}).get("version") == PRESET_VERSION,
              f"metadata={on_disk.get('metadata')}")
        entry = on_disk.get("tweaks", {}).get(tid.name)
        check("test tweak present in saved data", entry is not None)
        check("saved entry enabled", entry.get("enabled") is True)
        check("saved entry carries marker value",
              entry.get("value", {}).get(marker_key) == marker_value[marker_key])
        check("metadata round-trips fields",
              manager.get_preset_metadata("Audit76Real").get("description")
              == "round trip test")
        check("list_presets sees the preset",
              "Audit76Real" in manager.list_presets())

        # --- wipe the live state, load back, require exact restore ---
        tweak.set_enabled(original_enabled)
        tweak.value = copy.deepcopy(original_value)
        ok = manager.load_preset("Audit76Real")
        check("load_preset returns True", ok is True)
        check("live tweak enabled restored", tweak.enabled is True)
        check("live tweak value restored",
              tweak.value.get(marker_key) == marker_value[marker_key])

        # --- Fix Audit 43: legacy schemas rejected via the public API -
        def write_raw(name, payload):
            raw_path = manager.get_preset_path(name)
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            return raw_path

        write_raw("Audit76LegacyV1",
                  {"metadata": {"version": 1}, "tweaks": {}})
        ok = manager.load_preset("Audit76LegacyV1")
        check("version-1 preset rejected", ok is False)
        check("rejection names the unsupported version",
              manager.last_error is not None
              and "Unsupported preset version 1" in manager.last_error,
              f"last_error={manager.last_error!r}")

        write_raw("Audit76Versionless", {"tweaks": {}})
        ok = manager.load_preset("Audit76Versionless")
        check("version-less preset rejected", ok is False)
        check("rejection names the missing version field",
              manager.last_error is not None
              and "no version field" in manager.last_error,
              f"last_error={manager.last_error!r}")

        ok = manager.load_preset("Audit76DoesNotExist")
        check("missing preset rejected", ok is False)
        check("missing preset named in last_error",
              manager.last_error is not None
              and "Preset not found" in manager.last_error)

        # --- delete through the same real directory ------------------
        check("delete_preset removes the file",
              manager.delete_preset("Audit76Real") is True
              and not os.path.isfile(path))
    finally:
        # leave the global tweak dict exactly as it was found
        tweak.set_enabled(original_enabled)
        tweak.value = original_value

    print(f"\n{PASS} checks passed")


if __name__ == "__main__":
    main()
