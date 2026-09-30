#!/bin/sh
# Compile all Qt Linguist .ts files in this directory to .qm.
# Works on macOS, Linux and Windows (Git Bash / MSYS).
#
# Uses pyside6-lrelease from PATH, or from the repo venv at
# <repo>/.env if it exists. Pass LRELEASE=/path/to/lrelease to override.

set -eu
cd "$(dirname "$0")"

if [ -n "${LRELEASE:-}" ]; then
    LRELEASE_BIN="$LRELEASE"
elif [ -x "../../../.env/bin/pyside6-lrelease" ]; then
    LRELEASE_BIN="../../../.env/bin/pyside6-lrelease"
elif [ -x "../../../.env/Scripts/pyside6-lrelease.exe" ]; then
    LRELEASE_BIN="../../../.env/Scripts/pyside6-lrelease.exe"
else
    LRELEASE_BIN="pyside6-lrelease"
fi

count=0
for i in *.ts; do
    [ -f "$i" ] || break
    fnoext="${i%.*}.qm"
    "$LRELEASE_BIN" "$i" -qm "$fnoext"
    count=$((count + 1))
done
echo "Compiled $count translation file(s)."
