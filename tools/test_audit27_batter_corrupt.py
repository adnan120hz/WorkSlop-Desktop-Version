#!/usr/bin/env python3
"""Audit 27: corrupt .batter must not kill the whole template apply, and
parsing a template without a (device) version must not crash.

Guards:
1. TemplatesTweak.apply_tweak with a mix of one valid .batter and one
   .batter corrupted after load completes normally, stages the valid
   template's files, and reports the corrupt one per file in
   tweak.skipped_templates (never silently, never as applied).
2. An apply of only a corrupt .batter completes, stages nothing, and
   still reports the skip.
3. TemplateFile(path, device_version=None) with min_version/max_version in
   its config loads without crashing (Version(None) regression), and a
   config with no version fields loads the same way.
4. The version gate still bites when the device version IS known: a
   template requiring a newer iOS than the device raises
   PBTemplateException, not a pass.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit27_batter_corrupt.py
"""
import json
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication
_app = QCoreApplication.instance() or QCoreApplication(sys.argv)

from src.exceptions.posterboard_exceptions import PBTemplateException
from src.tweaks.posterboard.template_file import TemplateFile
from src.tweaks.posterboard.template_options.templates_tweak import TemplatesTweak

PASS = 0
TMP = tempfile.mkdtemp(prefix="audit27_")


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def make_batter(name, payload=b"audit27-payload", **config_overrides):
    """Minimal valid .batter: config.json + one container payload file."""
    config = {
        "options": [],
        "domain": "AppDomain-com.example.audit27",
        "format_version": 2,
        "title": name,
        "author": "audit27",
    }
    config.update(config_overrides)
    path = os.path.join(TMP, name)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("config.json", json.dumps(config))
        z.writestr("container/payload.txt", payload)
    return path


def test_mixed_apply_skips_corrupt_and_continues():
    print("\nMixed valid + corrupt .batter: apply finishes, corrupt reported per file")
    valid = TemplateFile(path=make_batter("valid.batter"), device_version="26.0")
    corrupt_path = make_batter("corrupt.batter")
    corrupt = TemplateFile(path=corrupt_path, device_version="26.0")
    # corrupt the file on disk after it was loaded (bit-rot / bad download)
    with open(corrupt_path, "wb") as f:
        f.write(b"this is not a zip archive at all")

    tweak = TemplatesTweak()
    tweak.templates = [corrupt, valid]  # corrupt first: must not stop the rest
    files_to_restore = []
    out_dir = os.path.join(TMP, "out_mixed")
    os.makedirs(out_dir)
    tweak.apply_tweak(files_to_restore=files_to_restore, output_dir=out_dir,
                      templates=tweak.templates, version="26.0",
                      force_pb_refresh=False)
    staged = [f for f in files_to_restore if f.restore_path.endswith("payload.txt")]
    check("apply completed and staged the valid template's payload", len(staged) == 1,
          f"staged={len(staged)}")
    check("valid payload bytes intact", staged and staged[0].contents == b"audit27-payload")
    check("corrupt template reported per file", len(tweak.skipped_templates) == 1,
          f"skipped={tweak.skipped_templates}")
    check("skip report names the corrupt file",
          tweak.skipped_templates and "corrupt.batter" in tweak.skipped_templates[0][0])
    check("skip report carries the real error, not a fake success",
          tweak.skipped_templates and len(tweak.skipped_templates[0][1]) > 0)


def test_only_corrupt_apply_completes_and_reports():
    print("\nOnly corrupt .batter: apply completes, stages nothing, reports the skip")
    corrupt_path = make_batter("only-corrupt.batter")
    corrupt = TemplateFile(path=corrupt_path, device_version="26.0")
    with open(corrupt_path, "wb") as f:
        f.write(b"\x00\x01garbage")

    tweak = TemplatesTweak()
    tweak.templates = [corrupt]
    files_to_restore = []
    out_dir = os.path.join(TMP, "out_only")
    os.makedirs(out_dir)
    tweak.apply_tweak(files_to_restore=files_to_restore, output_dir=out_dir,
                      templates=tweak.templates, version="26.0",
                      force_pb_refresh=False)
    check("nothing staged from a corrupt template", len(files_to_restore) == 0)
    check("skip still reported", len(tweak.skipped_templates) == 1)


def test_missing_device_version_does_not_crash():
    print("\nTemplate version parsing: missing device version is explicit, not a crash")
    gated = TemplateFile(
        path=make_batter("gated.batter", min_version="17.0", max_version="27.0"),
        device_version=None)
    check("min/max template loads with device_version=None",
          gated.min_version == "17.0" and gated.max_version == "27.0")
    ungated = TemplateFile(path=make_batter("ungated.batter"), device_version=None)
    check("template without version fields loads with device_version=None",
          ungated.min_version is None and ungated.max_version is None)
    empty = TemplateFile(
        path=make_batter("gated-empty.batter", min_version="17.0"),
        device_version="")
    check("empty device version string also safe", empty.min_version == "17.0")


def test_version_gate_still_enforced_when_known():
    print("\nVersion gate still honest when the device version is known")
    try:
        TemplateFile(path=make_batter("toonew.batter", min_version="99.0"),
                     device_version="16.0")
        raised = None
    except PBTemplateException as e:
        raised = e
    check("too-old device still rejected with PBTemplateException", raised is not None)
    try:
        TemplateFile(path=make_batter("tooold.batter", max_version="10.0"),
                     device_version="16.0")
        raised = None
    except PBTemplateException as e:
        raised = e
    check("too-new device still rejected with PBTemplateException", raised is not None)
    ok = TemplateFile(path=make_batter("inrange.batter", min_version="16.0",
                                       max_version="27.0"),
                      device_version="26.0")
    check("in-range template still loads", ok.name == "inrange.batter")


if __name__ == "__main__":
    test_mixed_apply_skips_corrupt_and_continues()
    test_only_corrupt_apply_completes_and_reports()
    test_missing_device_version_does_not_crash()
    test_version_gate_still_enforced_when_known()
    print(f"\n{PASS} checks passed")
