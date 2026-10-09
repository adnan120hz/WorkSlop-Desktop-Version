#!/usr/bin/env python3
"""CI test runner: every offscreen (device-free) test under ``tools/``.

Per Audit 77 the desktop CI used to build without running a single one of
the ``tools/test_*.py`` suites — regressions only surfaced when someone ran
a built binary. This runner is what the build workflow now executes first:
it discovers every ``tools/test_*.py`` and runs each one as a subprocess,
offscreen (``QT_QPA_PLATFORM=offscreen``), with a per-file timeout, so the
same checks a developer runs locally gate the workflow.

Tests that genuinely need a connected device do NOT belong in the default
run: add their file names to ``DEVICE_REQUIRED`` below. The remaining
suites are written to be device- and network-free (they exercise code with
real modules but no live hardware), and the whole offline set is expected
to finish in a couple of minutes.

Exit code is 0 only when every selected suite passed; any failure names
the offending files.

Run: python tools/run_offscreen_tests.py [--list-only]
"""

import glob
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Suites that need a real device attached. Empty today: every
# tools/test_*.py in the repo is designed to run with no phone connected.
# When a suite starts requiring hardware, list its basename here so CI
# keeps meaning "offscreen only" instead of silently skipping red tests.
DEVICE_REQUIRED = frozenset()

PER_FILE_TIMEOUT_S = 300


def collect_tests() -> list[str]:
    paths = sorted(glob.glob(os.path.join(ROOT, "tools", "test_*.py")))
    return [p for p in paths if os.path.basename(p) not in DEVICE_REQUIRED]


def main(argv: list[str]) -> int:
    tests = collect_tests()
    print(f"collected {len(tests)} offscreen test files")
    if "--list-only" in argv:
        for path in tests:
            print("  " + os.path.relpath(path, ROOT))
        return 0

    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    failures: list[str] = []
    for index, path in enumerate(tests, 1):
        name = os.path.relpath(path, ROOT)
        result = subprocess.run(
            [sys.executable, path],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=PER_FILE_TIMEOUT_S,
        )
        if result.returncode == 0:
            print(f"[{index}/{len(tests)}] OK   {name}", flush=True)
        else:
            print(f"[{index}/{len(tests)}] FAIL {name} (rc={result.returncode})",
                  flush=True)
            tail = result.stderr.decode("utf-8", "replace").strip().splitlines()
            for line in tail[-15:]:
                print("     " + line, flush=True)
            failures.append(name)

    print(f"\n{len(tests) - len(failures)}/{len(tests)} test files passed")
    if failures:
        print("failing: " + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
