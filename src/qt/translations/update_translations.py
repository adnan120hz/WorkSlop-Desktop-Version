#!/usr/bin/env python3
"""Extract translatable strings into the .ts files (pyside6-lupdate pipeline).

WorkSlop Desktop has no .pro file, so there is no canonical lupdate file
list anywhere else in this repo. This script IS the file list: it scans every
Python source file that can contain translatable strings and runs
pyside6-lupdate over them.

Usage:
    python update_translations.py [lang ...]
    # e.g. python update_translations.py id
    # with no args, all Nugget_*.ts files are updated.

IMPORTANT - the bare tr() convention:
    src/gui/ios/*.py define a module-level shim
        def tr(text): return QCoreApplication.translate("Nugget", text)
    (and src/gui/dialogs/app_list_dialog.py + src/gui/ios/passcode_theme.py
    use _tr() -> translate(_NUGGET, …) with _NUGGET = "Nugget").
    At runtime the lookup context is therefore "Nugget", but pyside6-lupdate
    files bare tr("...") calls into a context with NO name, where the runtime
    would never find them, and it cannot resolve translate(_NUGGET, "…") at
    all (variable context -> 0 texts extracted). After lupdate, this script
    post-processes every .ts: messages from the nameless context whose source
    is a genuine static tr("literal") call site (verified with ast, so
    f-string ghosts like 'Deleted {self.path}' are dropped) are moved into
    the "Nugget" context, and shim literals lupdate could never see are added
    straight to "Nugget" by the ast fallback pass.

The script never invents translations: new strings land as unfinished,
existing translations and their finished state are preserved.
"""
from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SRC_ROOT = os.path.join(REPO_ROOT, "src")

# Every module-level shim name that means QCoreApplication.translate("Nugget", …).
# lupdate files bare tr("…") into a NAMELESS context (fixed by post-processing
# below) and cannot resolve translate(_NUGGET, "…") at all (0 texts found),
# so _tr("…") literals are added to "Nugget" by the ast fallback pass.
TR_SHIM_NAMES = {"tr", "_tr"}


def iter_source_files() -> list[str]:
    """All Python files that may hold translatable strings, repo-rooted."""
    files: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(SRC_ROOT):
        # skip caches and vendored code
        _dirnames[:] = [
            d for d in _dirnames if d != "__pycache__" and d != "vendor"
        ]
        for fn in sorted(filenames):
            # resources_rc.py is the rcc-generated Qt resource blob: it
            # holds no translatable strings, and pyside6-lupdate segfaults
            # trying to parse it.
            if fn.endswith(".py") and fn != "resources_rc.py":
                files.append(os.path.join(dirpath, fn))
    for extra in ("main_app.py", "workslop_cli.py"):
        p = os.path.join(REPO_ROOT, extra)
        if os.path.isfile(p):
            files.append(p)
    return sorted(files)


def static_tr_literals(files: list[str]) -> dict[str, list[tuple[str, int]]]:
    """(source -> [(file, line)]) for string literals passed as first arg to a
    bare tr(…)/_tr(…) shim call. Implicit concatenation ("a" "b") is already
    folded by the parser, so the key is the exact runtime lookup string."""
    out: dict[str, list[tuple[str, int]]] = {}
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=path)
        except (OSError, SyntaxError):
            continue
        rel = os.path.relpath(path, HERE)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in TR_SHIM_NAMES
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                out.setdefault(node.args[0].value, []).append(
                    (rel, node.lineno)
                )
    return out


def find_lupdate() -> str | None:
    override = os.environ.get("LUPDATE")
    if override:
        return override
    return shutil.which("pyside6-lupdate")


def move_nameless_to_nugget(
    ts_path: str, literals: dict[str, list[tuple[str, int]]]
) -> tuple[int, int, int]:
    """Move nameless-context messages into "Nugget".

    Then the ast fallback pass: any shim literal (tr()/​_tr()) that lupdate
    could not see at all — e.g. translate(_NUGGET, "…") with a variable
    context — is added straight to "Nugget" as unfinished, unless the same
    source already lives in some other named context (e.g. via self.tr()).

    Returns (moved, dropped, ast_added).
    """
    tree = ET.parse(ts_path)
    root = tree.getroot()
    nameless = None
    nugget = None
    for ctx in root.findall("context"):
        name_el = ctx.find("name")
        if name_el is None or (name_el.text or "").strip() == "":
            nameless = ctx
        elif (name_el.text or "").strip() == "Nugget":
            nugget = ctx
    if nugget is None:
        nugget = ET.SubElement(root, "context")
        ET.SubElement(nugget, "name").text = "Nugget"

    existing = {}
    for m in nugget.findall("message"):
        s = m.find("source")
        if s is not None:
            existing[s.text or ""] = m
    moved = dropped = 0
    for msg in list(nameless.findall("message")) if nameless is not None else []:
        src_el = msg.find("source")
        src = src_el.text or "" if src_el is not None else ""
        if src not in literals:
            # f-string ghost or non-literal: not runtime-reachable
            dropped += 1
            continue
        nug_msg = existing.get(src)
        if nug_msg is None:
            # keep lupdate's <location> entries, drop nothing else
            nugget.append(msg)
            existing[src] = msg
            moved += 1
            continue
        # Duplicate: the string is still used (via bare tr()), so the Nugget
        # entry must NOT stay vanished/obsolete, or lrelease would drop a
        # perfectly good translation from the .qm.
        tr_el = nug_msg.find("translation")
        if tr_el is not None and tr_el.get("type") in ("vanished", "obsolete"):
            del tr_el.attrib["type"]
        for loc in nug_msg.findall("location"):
            nug_msg.remove(loc)
        for loc in msg.findall("location"):
            nug_msg.append(loc)
        dropped += 1
    if nameless is not None:
        root.remove(nameless)

    # ast fallback: shim literals lupdate could never see (variable context).
    all_sources: set[str] = set()
    for ctx in root.findall("context"):
        for m in ctx.findall("message"):
            s = m.find("source")
            if s is not None:
                all_sources.add(s.text or "")
    ast_added = 0
    for src, locs in literals.items():
        if src in all_sources:
            continue
        msg = ET.SubElement(nugget, "message")
        # newest call site first, like lupdate ordering
        for filename, line in sorted(set(locs), reverse=True)[:3]:
            ET.SubElement(msg, "location", {
                "filename": filename, "line": str(line)})
        ET.SubElement(msg, "source").text = src
        ET.SubElement(msg, "translation", {"type": "unfinished"})
        ast_added += 1

    ET.indent(tree, space="  ")
    tree.write(ts_path, encoding="utf-8", xml_declaration=True)
    return moved, dropped, ast_added


def main(argv: list[str]) -> int:
    lupdate = find_lupdate()
    if not lupdate:
        print(
            "error: could not find pyside6-lupdate.\n"
            "Install it with:  pip install PySide6\n"
            "or set LUPDATE=/path/to/pyside6-lupdate",
            file=sys.stderr,
        )
        return 127

    if argv:
        ts_files = [os.path.join(HERE, f"Nugget_{code}.ts") for code in argv]
        missing = [p for p in ts_files if not os.path.isfile(p)]
        if missing:
            print(f"error: not found: {', '.join(missing)}", file=sys.stderr)
            return 2
    else:
        ts_files = sorted(
            os.path.join(HERE, f)
            for f in os.listdir(HERE)
            if f.startswith("Nugget_") and f.endswith(".ts")
        )
    if not ts_files:
        print("No .ts files found.", file=sys.stderr)
        return 1

    sources = iter_source_files()
    print(f"Scanning {len(sources)} source files...")
    # lupdate wants paths relative to the .ts directory for stable <location>s
    rel_sources = [os.path.relpath(p, HERE) for p in sources]
    literals = static_tr_literals(sources)

    # registry.py titles use QT_TRANSLATE_NOOP("Nugget", ...) - keep it scanned
    if not any(p.endswith("src/tweaks/registry.py") for p in sources):
        print("error: src/tweaks/registry.py missing from lupdate file list!",
              file=sys.stderr)
        return 2

    for ts in ts_files:
        print(f"--- {os.path.basename(ts)}")
        r = subprocess.run(
            [lupdate, *rel_sources, "-ts", os.path.basename(ts)],
            cwd=HERE,
            capture_output=True,
            text=True,
        )
        if r.stdout.strip():
            print(r.stdout.strip())
        if r.stderr.strip():
            # lupdate reports skips/refusals on stderr with rc 0; surface them
            print(f"    [lupdate stderr] {r.stderr.strip()}", file=sys.stderr)
        if r.returncode != 0:
            print(f"FAILED: {ts}\n{r.stderr.strip()}", file=sys.stderr)
            return 1
        moved, dropped, ast_added = move_nameless_to_nugget(ts, literals)
        print(f"    post-process: moved {moved} to 'Nugget', "
              f"dropped {dropped}, ast-added {ast_added}")
    print("Done. New strings are unfinished - translate them, then run")
    print("compile_languages.sh (or compile_languages.py) to rebuild the .qm.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
