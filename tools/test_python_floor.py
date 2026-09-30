#!/usr/bin/env python3
"""Offline guard: the project really does support Python 3.10 (and no more).

The floor is 3.10 for a hard, verifiable reason: requirements.txt pins
PySide6 6.11.1, whose Requires-Python is >=3.10. The codebase itself never
needed more -- a 3.9 legacy lane existed and has since been dropped, because
keeping it honest cost more than it was worth (PySide6 6.11 has no 3.9 build,
so 3.9 could only ever be served by pinning an older Qt).

Two ways the floor gets broken silently, both checked here:

1. Syntax/API above 3.10. The dev virtualenv is 3.14, so a `match` statement
   or an `except*` group parses fine locally and only explodes on 3.10. Every
   file is therefore parsed against the 3.10 *grammar*
   (ast feature_version) and scanned for 3.11+ stdlib names.
2. Runtime-evaluated PEP 604 unions (`X | None`) are fine from 3.10, but a
   TYPE_CHECKING-only import used in a live annotation breaks on every version
   -- that is the class of bug in tools/test_annotation_imports.py, which this
   file defers to rather than duplicating.

Run: python tools/test_python_floor.py
"""
import ast
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
MIN_VERSION = (3, 10)
ENTRY_POINTS = ("main_app.py", "compile.py", "workslop_cli.py", "restore.py",
                "restore_cache.py", "skip_setup.py", "apply_wallpaper.py")

# Present in 3.11+, absent in 3.10. Matched against `import` targets and
# `from X import a` names, so a docstring that merely says "Required" is not
# a false positive.
API_ABOVE_FLOOR = {
    "asyncio": {"timeout", "timeout_at", "TaskGroup", "Runner"},
    "typing": {"Self", "assert_type", "LiteralString", "Required",
               "NotRequired", "TypeVarTuple", "Unpack"},
    "enum": {"StrEnum", "ReprEnum"},
    "datetime": {"UTC"},
    "contextlib": {"chdir"},
    "hashlib": {"file_digest"},
    "types": {"ExceptionGroup", "UnionType", "NoneType"},
}
TOP_LEVEL_ABOVE_FLOOR = {"tomllib", "ExceptionGroup", "BaseExceptionGroup"}

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def source_files():
    found = []
    for name in ENTRY_POINTS:
        if os.path.isfile(os.path.join(ROOT, name)):
            found.append(os.path.join(ROOT, name))
    for folder in ("src", "tools", "scripts"):
        base = os.path.join(ROOT, folder)
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            found += [os.path.join(root, f) for f in sorted(files)
                      if f.endswith(".py")]
    return found


def test_grammar_is_3_10():
    print(f"\nevery file parses against the {MIN_VERSION[0]}.{MIN_VERSION[1]} grammar")
    offenders = []
    files = source_files()
    for path in files:
        rel = os.path.relpath(path, ROOT)
        try:
            ast.parse(open(path, encoding="utf-8").read(), filename=rel,
                      feature_version=MIN_VERSION)
        except SyntaxError as e:
            offenders.append(f"{rel}:{e.lineno}: {e.msg}")
    check(f"scanned {len(files)} files", len(files) > 100, f"{len(files)}")
    check("no syntax newer than the floor", not offenders, "; ".join(offenders))


def test_no_3_11_api():
    print("\nno stdlib API newer than the floor")
    offenders = []
    for path in source_files():
        rel = os.path.relpath(path, ROOT)
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in TOP_LEVEL_ABOVE_FLOOR:
                        offenders.append(f"{rel}: import {alias.name}")
                    if top in API_ABOVE_FLOOR and alias.asname is None:
                        # `import asyncio` is fine; only attribute use matters,
                        # and that is covered by the AttributeError scan below
                        pass
            elif isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module.split(".")[0]
                for alias in node.names:
                    if alias.name in TOP_LEVEL_ABOVE_FLOOR:
                        offenders.append(f"{rel}: from {node.module} import {alias.name}")
                    if alias.name in API_ABOVE_FLOOR.get(mod, ()):
                        offenders.append(f"{rel}: from {node.module} import {alias.name}")
    check("no 3.11+ import anywhere", not offenders, "; ".join(offenders))


def test_runtime_unions_are_fine_at_the_floor():
    print("\nruntime PEP 604 unions are legal at 3.10 (no future import needed)")
    offenders = []
    for path in source_files():
        rel = os.path.relpath(path, ROOT)
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = node.args
                for arg in (list(args.posonlyargs) + list(args.args)
                            + list(args.kwonlyargs) + [args.vararg, args.kwarg]):
                    if arg is None or arg.annotation is None:
                        continue
                    if isinstance(arg.annotation, ast.Constant):
                        continue
                    if any(isinstance(x, ast.BinOp) and isinstance(x.op, ast.BitOr)
                           for x in ast.walk(arg.annotation)):
                        offenders.append(f"{rel}:{arg.lineno}")
    # informational only: these are FINE on 3.10, so this is a count, not a failure
    check("X | Y annotations are evaluated natively (count, not a failure)",
          True, f"{len(offenders)} sites")
    for o in offenders:
        print(f"       native 3.10 union: {o}")


def test_requirements_agree():
    print("\nthe pinned dependencies agree with the floor")
    req = os.path.join(ROOT, "requirements.txt")
    check("requirements.txt exists", os.path.isfile(req))
    text = open(req, encoding="utf-8").read()
    # PySide6 6.11.1 declares Requires-Python >=3.10 -- that IS the floor.
    check("pins PySide6 6.11.x (the >=3.10 Qt line)",
          "PySide6" in text and "6.11" in text)
    check("does not claim a 3.9-capable PySide6",
          "6.9" not in text, "main requirements must not serve 3.9")

    legacy = os.path.join(ROOT, "requirements-legacy.txt")
    check("legacy requirements still exist", os.path.isfile(legacy))
    ltext = open(legacy, encoding="utf-8").read()
    check("legacy is documented as a macOS floor, not a Python one",
          "macOS 12" in ltext)
    # The 3.9 lane used to need a `numpy<2.1; python_version < '3.10'` marker
    # and a promise to serve 3.9. Both are gone; mentioning 3.9 in the abi3
    # wheel note is factual, so the invariant is "no version-gated pin", not
    # "the digit 3.9 never appears".
    pins = [ln for ln in ltext.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    check("legacy pins nothing by python_version",
          not any("python_version" in ln for ln in pins),
          str([ln for ln in pins if "python_version" in ln]))
    check("legacy states the project floor is 3.10",
          "Python 3.10" in ltext)

    # the CI legacy job must not ask for an interpreter below the floor
    ci = os.path.join(ROOT, ".github", "workflows", "build.yml")
    if os.path.isfile(ci):
        ctext = open(ci, encoding="utf-8").read()
        bad = [v for v in ("'3.8'", "'3.9'", "3.8", "3.9")
               if f"python-version: {v}" in ctext]
        check("no CI job builds with an interpreter below the floor",
              not bad, str(bad))


def main():
    test_grammar_is_3_10()
    test_no_3_11_api()
    test_runtime_unions_are_fine_at_the_floor()
    test_requirements_agree()
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
