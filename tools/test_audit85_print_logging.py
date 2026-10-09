#!/usr/bin/env python3
"""Fix Audit 85: GUI-runtime print() calls go through logging.

* No ``print(`` remains in ``src/gui/**``,
  ``src/devicemanagement/device_manager.py`` or the GUI-called runtime
  modules (controllers / crash handler / restore / posterboard tweaks).
  The only survivors outside that scope are the logging bootstrap's own
  stderr fallback and a docstring example — both listed explicitly.
* ``device_manager.get_files_list_str`` no longer prints the file list
  on apply errors (the list is returned for the alert detail instead);
* ``show_apply_error`` logs the traceback at error level;
* a representative converted call site actually emits a log record.

CLI prints (``src/cli/**``) and the vendored engine
(``src/sideload/ipaside_engine/**``) are out of scope by design.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python \
    tools/test_audit85_print_logging.py
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0
ROOT = os.path.join(os.path.dirname(__file__), "..")


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def read(rel):
    with open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8") as f:
        return f.read()


def count_prints(rel):
    return read(rel).count("print(")


print("\nno print() left in the GUI runtime scope")
GUI_FILES = []
for base, _dirs, files in os.walk(os.path.join(ROOT, "src", "gui")):
    for name in files:
        if name.endswith(".py"):
            GUI_FILES.append(os.path.relpath(
                os.path.join(base, name), ROOT).replace(os.sep, "/"))
check("gui scope is non-empty", len(GUI_FILES) > 10, str(len(GUI_FILES)))
for rel in sorted(GUI_FILES):
    check(f"no print: {rel}", count_prints(rel) == 0)

RUNTIME_FILES = [
    "src/devicemanagement/device_manager.py",
    "src/controllers/hotload.py",
    "src/controllers/preset_manager.py",
    "src/controllers/video_handler.py",
    "src/exceptions/crash_handler.py",
    "src/restore/restore.py",
    "src/restore/__init__.py",
    "src/restore/protective.py",
    "src/tweaks/eligibility_tweak.py",
    "src/tweaks/posterboard/pb_config_manager.py",
    "src/tweaks/posterboard/posterboard_tweak.py",
    "src/tweaks/posterboard/template_file.py",
    "src/tweaks/posterboard/template_options/templates_tweak.py",
]
for rel in RUNTIME_FILES:
    check(f"no print: {rel}", count_prints(rel) == 0)

print("\ndevice_manager: file list returned, never printed; errors logged")
import io  # noqa: E402
from contextlib import redirect_stdout  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import src.devicemanagement.device_manager as dm  # noqa: E402

buf = io.StringIO()
fake = [SimpleNamespace(domain="D1", restore_path="p1"),
        SimpleNamespace(domain="D2", restore_path="p2")]
with redirect_stdout(buf):
    text = dm.get_files_list_str(fake)
check("file list text still returned",
      "D1" in text and "p2" in text, text)
check("nothing printed for the file list", buf.getvalue() == "",
      repr(buf.getvalue()))

records = []


class _Cap(logging.Handler):
    def emit(self, record):
        records.append(record)


# device_manager logs through the protective helpers (GoldenNugget.*).
for name in ("GoldenNugget.protective", "WorkSlop.crash"):
    logging.getLogger(name).addHandler(_Cap())
    logging.getLogger(name).setLevel(logging.DEBUG)
buf = io.StringIO()
with redirect_stdout(buf):
    try:
        raise RuntimeError("apply boom")
    except RuntimeError as exc:
        dm.show_apply_error(exc)
check("show_apply_error prints nothing", buf.getvalue() == "",
      repr(buf.getvalue()))
check("show_apply_error logged the traceback",
      any("apply boom" in r.getMessage() or "RuntimeError" in r.getMessage()
          for r in records), repr([r.getMessage()[:40] for r in records]))

print("\nhotload update failure is an error log, not a print")
import src.controllers.hotload as hl  # noqa: E402

hl_records = []


class _HCap(logging.Handler):
    def emit(self, record):
        hl_records.append(record.getMessage())


_hlog = logging.getLogger("WorkSlop.hotload")
_hlog.addHandler(_HCap())
_hlog.setLevel(logging.DEBUG)
inst = object.__new__(hl.HotLoad)
inst.settings = None
inst._rules = {"version": 0, "rules": []}
inst._rules_available = True
inst._rules_error = None
# A file:// URL that cannot be fetched exercises the error branch.
ok = inst.update(url="file:///nonexistent-hotload-rules.json")
check("failed fetch returns False", ok is False)
check("failed fetch logged at error text",
      any("update failed" in m for m in hl_records), repr(hl_records))

print(f"\nALL {PASS} CHECKS PASSED")
