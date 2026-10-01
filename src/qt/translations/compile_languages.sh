#!/bin/sh
# Compile all Qt Linguist .ts files in this directory to .qm.
# Works on macOS, Linux and Windows (Git Bash / MSYS).
#
# From Windows cmd / PowerShell this script cannot run (no sh): use the
# cross-platform companion instead:
#     python compile_languages.py
#
# lrelease resolution order:
#   1. $LRELEASE env var (explicit override)
#   2. $VIRTUAL_ENV/bin/pyside6-lrelease            (active venv, macOS/Linux)
#   3. $VIRTUAL_ENV/Scripts/pyside6-lrelease.exe    (active venv, Windows)
#   4. <repo>/.env/bin/pyside6-lrelease             (repo venv, macOS/Linux)
#   5. <repo>/.env/Scripts/pyside6-lrelease.exe     (repo venv, Windows)
#   6. pyside6-lrelease from PATH
#
# A file that fails to compile does NOT abort the run: failures are collected
# and reported at the end, and the script exits non-zero if any failed.

set -eu
cd "$(dirname "$0")"

if [ -n "${LRELEASE:-}" ]; then
    LRELEASE_BIN="$LRELEASE"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/pyside6-lrelease" ]; then
    LRELEASE_BIN="$VIRTUAL_ENV/bin/pyside6-lrelease"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/Scripts/pyside6-lrelease.exe" ]; then
    LRELEASE_BIN="$VIRTUAL_ENV/Scripts/pyside6-lrelease.exe"
elif [ -x "../../../.env/bin/pyside6-lrelease" ]; then
    LRELEASE_BIN="../../../.env/bin/pyside6-lrelease"
elif [ -x "../../../.env/Scripts/pyside6-lrelease.exe" ]; then
    LRELEASE_BIN="../../../.env/Scripts/pyside6-lrelease.exe"
else
    LRELEASE_BIN="pyside6-lrelease"
fi

if ! command -v "$LRELEASE_BIN" >/dev/null 2>&1; then
    echo "error: could not find pyside6-lrelease (tried: $LRELEASE_BIN)" >&2
    echo "Install it with:  pip install PySide6" >&2
    echo "or activate the venv that has it, or set LRELEASE=/path/to/pyside6-lrelease" >&2
    exit 127
fi

count=0
failed=0
failed_list=""
for i in *.ts; do
    [ -f "$i" ] || break
    fnoext="${i%.*}.qm"
    if "$LRELEASE_BIN" "$i" -qm "$fnoext"; then
        count=$((count + 1))
    else
        echo "FAILED: $i" >&2
        failed=$((failed + 1))
        failed_list="${failed_list} $i"
    fi
done

echo "Compiled $count translation file(s)."
if [ "$failed" -gt 0 ]; then
    echo "error: $failed file(s) failed to compile:$failed_list" >&2
    exit 1
fi
