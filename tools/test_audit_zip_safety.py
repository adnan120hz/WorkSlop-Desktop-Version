#!/usr/bin/env python3
"""Round-9 audit: untrusted-archive safety (PosterBoard/icon themes).

User-supplied .tendies/.passthm/icon-theme archives flow through
src/utils/zip_safe.py. Pins: traversal and absolute members are
skipped (never written outside dest), good members extract, safe_join
refuses escapes, and device restore paths reject ``..`` segments.

Run: python tools/test_audit_zip_safety.py
"""
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.utils.zip_safe import (
    assert_device_path_safe, is_within_directory, safe_extractall,
    safe_join)

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    print("\nround-9: zip/path safety")
    with tempfile.TemporaryDirectory() as tmp:
        evil_zip = os.path.join(tmp, "evil.zip")
        with zipfile.ZipFile(evil_zip, "w") as zf:
            zf.writestr("good/file.txt", "ok")
            zf.writestr("../escape.txt", "bad")
            zf.writestr("sub/../../escape2.txt", "bad")
            zf.writestr("/abs.txt", "bad")
        dest = os.path.join(tmp, "dest")
        os.makedirs(dest)
        with zipfile.ZipFile(evil_zip) as zf:
            skipped = safe_extractall(zf, dest)
        check("traversal members skipped", len(skipped) == 3, str(skipped))
        check("good member extracted",
              open(os.path.join(dest, "good", "file.txt")).read() == "ok")
        check("nothing written outside dest",
              not os.path.exists(os.path.join(tmp, "escape.txt"))
              and not os.path.exists(os.path.join(tmp, "escape2.txt")))

        try:
            safe_join(dest, "..", "x")
            raised = False
        except ValueError:
            raised = True
        check("safe_join refuses escape", raised)
        check("safe_join allows inside paths",
              safe_join(dest, "a", "b").startswith(dest))
        check("within-directory logic",
              is_within_directory(dest, os.path.join(dest, "x"))
              and not is_within_directory(dest, tmp))

        check("device path guard accepts normal path",
              assert_device_path_safe("Library/Preferences/x.plist"))
        try:
            assert_device_path_safe("../etc/passwd")
            raised = False
        except ValueError:
            raised = True
        check("device path guard rejects .. segments", raised)

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
