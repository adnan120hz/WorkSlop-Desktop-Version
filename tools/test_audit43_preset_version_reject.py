#!/usr/bin/env python3
"""Fix Audit 43: legacy preset schemas are rejected with a version message.

Before: PresetManager accepted v1 / pre-metadata presets (no
metadata.version field) silently. Now load/import reject them with an
"Unsupported preset version ..." message naming the version, exposed to
callers via PresetManager.last_error (load returns False rather than
raising, so the shared GUI load flow shows its failure dialog instead of
crashing), while current-format (version 2) presets keep loading.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit43_preset_version_reject.py
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

from src.controllers.preset_manager import (  # noqa: E402
    PresetManager, UnsupportedPresetVersionError, PRESET_VERSION,
)

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


def write_preset(pm, name, data):
    with open(pm.get_preset_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f)


# =============================================================================
def test_version_gate(tmpdir):
    print("\nload: legacy schemas rejected, current format passes")
    pm = make_manager(tmpdir)

    check("current format saves", pm.save_preset("Current") is True)
    check("current format loads", pm.load_preset("Current") is True)
    check("no error recorded for current format", pm.last_error is None)

    write_preset(pm, "V1", {"metadata": {"version": 1}, "tweaks": {}})
    check("v1 preset rejected", pm.load_preset("V1") is False)
    check("v1 rejection names the unsupported version",
          pm.last_error is not None
          and "Unsupported preset version" in pm.last_error
          and "1" in pm.last_error, str(pm.last_error))

    write_preset(pm, "PreMeta", {"tweaks": {}})
    check("pre-metadata preset rejected", pm.load_preset("PreMeta") is False)
    check("pre-metadata rejection names the missing version",
          pm.last_error is not None
          and "Unsupported preset version" in pm.last_error,
          str(pm.last_error))

    write_preset(pm, "NoVersion",
                 {"metadata": {"description": "x"}, "tweaks": {}})
    check("metadata without version rejected",
          pm.load_preset("NoVersion") is False)
    check("missing-version rejection is explicit",
          pm.last_error is not None
          and "no version" in pm.last_error, str(pm.last_error))

    write_preset(pm, "Future", {"metadata": {"version": 99}, "tweaks": {}})
    check("future version rejected", pm.load_preset("Future") is False)
    check("future rejection names version 99",
          pm.last_error is not None and "99" in pm.last_error,
          str(pm.last_error))

    # The validator itself raises the informative exception for direct users.
    try:
        PresetManager._validate_preset_version({"tweaks": {}})
        raised = None
    except UnsupportedPresetVersionError as e:
        raised = str(e)
    check("validator raises UnsupportedPresetVersionError",
          raised is not None and "Unsupported preset version" in raised,
          str(raised))
    check("supported version constant is what save writes",
          PresetManager._data_preset_version(
              {"metadata": {"version": PRESET_VERSION}}) == PRESET_VERSION)


# =============================================================================
def test_import_gate(tmpdir):
    print("\nimport: legacy file rejected with the version message")
    pm = make_manager(tmpdir)
    old_path = os.path.join(tmpdir, "old-export.json")
    with open(old_path, "w", encoding="utf-8") as f:
        json.dump({"tweaks": {}}, f)
    ok, msg = pm.import_preset(old_path)
    check("legacy import rejected", ok is False)
    check("legacy import message names the version problem",
          "Unsupported preset version" in msg, msg)

    check("current format saves for export", pm.save_preset("Src") is True)
    export_path = os.path.join(tmpdir, "current-export.json")
    check("export succeeds", pm.export_preset("Src", export_path) is True)
    ok, name = pm.import_preset(export_path)
    check("current-format import accepted", ok is True, str((ok, name)))


# =============================================================================
class FakeBox:
    class StandardButton:
        Yes = 1
        Cancel = 2

    calls = []
    question_reply = StandardButton.Yes

    @classmethod
    def reset(cls):
        cls.calls = []
        cls.question_reply = cls.StandardButton.Yes

    @classmethod
    def question(cls, parent, title, text, *a, **kw):
        cls.calls.append(("question", title, text))
        return cls.question_reply

    @classmethod
    def warning(cls, parent, title, text, *a, **kw):
        cls.calls.append(("warning", title, text))

    @classmethod
    def information(cls, parent, title, text, *a, **kw):
        cls.calls.append(("information", title, text))

    @classmethod
    def critical(cls, parent, title, text, *a, **kw):
        cls.calls.append(("critical", title, text))


class FakeSettings:
    def __init__(self):
        self.values = {}

    def setValue(self, key, value):
        self.values[key] = value

    def value(self, key, default=None, type=None):
        return self.values.get(key, default)


class FakeDM:
    def get_current_device_version(self):
        return "26.6.1"

    def get_current_device_model(self):
        return "iPhone14,5"

    def get_current_device_build(self):
        return "23G83"


def test_gui_flow_shows_failure_not_crash(tmpdir):
    print("\nGUI load flow: legacy preset -> failure dialog, no crash")
    import src.gui.ios.preset_menu as preset_mod

    pm = make_manager(tmpdir)
    write_preset(pm, "Legacy", {"tweaks": {}})

    window = SimpleNamespace(
        apply_in_progress=False, _cache_restore_in_progress=False,
        _gestalt_apply_in_progress=False, _full_restore_in_progress=False,
        _gestalt_apply_thread=None, _full_restore_thread=None,
        _ios_page_objs={}, settings=FakeSettings(), device_manager=FakeDM())
    window._sync_settings = lambda: None

    saved_box, saved_restart = preset_mod.QMessageBox, preset_mod.restart_app
    preset_mod.QMessageBox = FakeBox
    preset_mod.restart_app = lambda: (_ for _ in ()).throw(
        AssertionError("restart must not run for a rejected preset"))
    FakeBox.reset()
    try:
        result = preset_mod.load_preset_flow(None, window, pm, "Legacy")
    finally:
        preset_mod.QMessageBox, preset_mod.restart_app = saved_box, saved_restart

    check("flow returns False for a legacy preset", result is False)
    check("flow showed the failure dialog (did not crash)",
          any(kind == "critical" for kind, _t, _x in FakeBox.calls),
          str(FakeBox.calls))
    check("version message reached the caller via last_error",
          pm.last_error is not None
          and "Unsupported preset version" in pm.last_error,
          str(pm.last_error))
    check("failure dialog shows the specific version message",
          any(kind == "critical" and "Unsupported preset version" in text
              for kind, _t, text in FakeBox.calls),
          str(FakeBox.calls))
    check("failure dialog is not the generic text",
          not any(kind == "critical" and text == "Failed to load the preset."
                  for kind, _t, text in FakeBox.calls),
          str(FakeBox.calls))


def main():
    tmpdir = tempfile.mkdtemp(prefix="audit43-")
    test_version_gate(tmpdir)
    test_import_gate(tmpdir)
    test_gui_flow_shows_failure_not_crash(tmpdir)
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
