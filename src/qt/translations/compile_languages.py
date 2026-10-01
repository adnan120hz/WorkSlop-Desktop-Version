#!/usr/bin/env python3
"""Compile all Qt Linguist .ts files in this directory to .qm.

Cross-platform companion to compile_languages.sh (which needs sh, so it
cannot run from Windows cmd / PowerShell). Run from anywhere:

    python src/qt/translations/compile_languages.py

lrelease resolution order (same as the .sh):
  1. $LRELEASE env var (explicit override)
  2. $VIRTUAL_ENV/bin/pyside6-lrelease            (active venv, macOS/Linux)
  3. $VIRTUAL_ENV/Scripts/pyside6-lrelease.exe   (active venv, Windows)
  4. <repo>/.env/bin/pyside6-lrelease            (repo venv, macOS/Linux)
  5. <repo>/.env/Scripts/pyside6-lrelease.exe    (repo venv, Windows)
  6. pyside6-lrelease from PATH

A file that fails to compile does NOT abort the run: failures are collected
and reported at the end; exit code is 1 if any failed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def find_lrelease() -> str | None:
    override = os.environ.get("LRELEASE")
    if override:
        return override
    venv = os.environ.get("VIRTUAL_ENV")
    candidates: list[str] = []
    if venv:
        candidates.append(os.path.join(venv, "bin", "pyside6-lrelease"))
        candidates.append(os.path.join(venv, "Scripts", "pyside6-lrelease.exe"))
    candidates.append(os.path.join(REPO_ROOT, ".env", "bin", "pyside6-lrelease"))
    candidates.append(
        os.path.join(REPO_ROOT, ".env", "Scripts", "pyside6-lrelease.exe")
    )
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
        # On Windows, executability bits are meaningless; accept existing file.
        if os.path.isfile(c) and os.name == "nt":
            return c
    return shutil.which("pyside6-lrelease")


def main() -> int:
    lrelease = find_lrelease()
    if not lrelease:
        print(
            "error: could not find pyside6-lrelease.\n"
            "Install it with:  pip install PySide6\n"
            "or activate the venv that has it, "
            "or set LRELEASE=/path/to/pyside6-lrelease",
            file=sys.stderr,
        )
        return 127

    ts_files = sorted(f for f in os.listdir(HERE) if f.endswith(".ts"))
    if not ts_files:
        print("No .ts files found in", HERE)
        return 0

    compiled = 0
    failed: list[str] = []
    for ts in ts_files:
        qm = os.path.splitext(ts)[0] + ".qm"
        print(f"--- {ts} -> {qm}")
        try:
            r = subprocess.run(
                [lrelease, ts, "-qm", qm],
                cwd=HERE,
                capture_output=True,
                text=True,
            )
        except OSError as e:
            print(f"FAILED to launch lrelease for {ts}: {e}", file=sys.stderr)
            failed.append(ts)
            continue
        if r.stdout.strip():
            print(r.stdout.strip())
        if r.returncode != 0:
            print(f"FAILED: {ts}\n{r.stderr.strip()}", file=sys.stderr)
            failed.append(ts)
        else:
            if r.stderr.strip():
                print(r.stderr.strip(), file=sys.stderr)
            compiled += 1

    print(f"Compiled {compiled} translation file(s).")
    if failed:
        print(
            f"error: {len(failed)} file(s) failed to compile: "
            + " ".join(failed),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
