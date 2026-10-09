#!/usr/bin/env python3
"""Audit 86: cv2/ffmpeg must not be dragged into startup.

Runs the import in a fresh interpreter (sys.modules state is the
evidence) and checks:

* importing ``src.controllers.video_handler`` — which the Settings
  page and the main window do only for ``set_ignore_frame_limit`` —
  does not import cv2/ffmpeg and does not print the old
  "failed to include cv2!" noise;
* the trivial setter still works;
* calling a video feature without the libraries fails with a clear,
  honest error (when the libraries genuinely are unavailable), and
  loads them lazily when they are available.

Run: ~/wsvenv/bin/python tools/test_audit86_lazy_cv2.py
"""
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


CHILD = r"""
import sys, time
t0 = time.perf_counter()
import src.controllers.video_handler as vh
ms = (time.perf_counter() - t0) * 1000.0
print(f"import_ms={ms:.1f}")
assert 'cv2' not in sys.modules, 'cv2 leaked into startup import'
assert 'ffmpeg' not in sys.modules, 'ffmpeg leaked into startup import'
assert vh.cv2_successful is False, 'cv2_successful should start False'
vh.set_ignore_frame_limit(True)
assert vh.ignore_pb_frame_limit is True
vh.set_ignore_frame_limit(False)
if vh._load_video_libs():
    assert 'cv2' in sys.modules, 'lazy load should import cv2 on demand'
    print("libs available: lazy load imported them on first use")
else:
    try:
        vh.create_caml("nope.mp4", "out", False, "linear")
    except RuntimeError as e:
        assert "unavailable" in str(e), str(e)
        print("libs missing: create_caml raised a clear RuntimeError")
    else:
        raise AssertionError("create_caml should fail without cv2/ffmpeg")
print("child ok")
"""

out = subprocess.run(
    [sys.executable, "-c", CHILD], cwd=ROOT,
    capture_output=True, text=True, timeout=180)
print(out.stdout.strip())
check("child interpreter passed", out.returncode == 0,
      out.stderr.strip().splitlines()[-1] if out.stderr.strip() else "")
check("no startup noise", "failed to include cv2" not in out.stdout)
import_line = [ln for ln in out.stdout.splitlines()
               if ln.startswith("import_ms=")]
check("import timing reported", len(import_line) == 1,
      import_line[0] if import_line else "missing")

print(f"\nALL {PASS} CHECKS PASSED")
