"""Shared filesystem safety helpers: zip-slip (CWE-22) and path-traversal guards.

PosterBoard template/tendie handling deals with user-supplied archives and
``config.json`` files, i.e. untrusted input. These helpers are the single
implementation used by every call site so the guard cannot drift between
copies.
"""

from __future__ import annotations

import glob as _glob
import os
import zipfile


def _canonical(path: str) -> str:
    # normcase matters on Windows (case-insensitive FS); identity on POSIX.
    return os.path.normcase(os.path.realpath(path))


def is_within_directory(base: str, target: str) -> bool:
    """True when *target* is *base* itself or lives under it.

    Uses realpath(), so a symlink inside *base* pointing outside is correctly
    reported as outside.
    """
    base_c = _canonical(base)
    target_c = _canonical(target)
    return target_c == base_c or target_c.startswith(base_c + os.sep)


def safe_extractall(zf: zipfile.ZipFile, dest: str) -> list[str]:
    """zipfile extractall() with a zip-slip guard (CWE-22).

    A crafted archive can carry entries like ``../../evil.sh`` or absolute
    paths that a plain extractall() would write outside *dest*. Every member
    is validated first; anything absolute or escaping *dest* is skipped and
    reported in the returned skip list.
    """
    skipped: list[str] = []
    dest_c = _canonical(dest)
    for member in zf.infolist():
        name = member.filename
        if os.path.isabs(name):
            skipped.append(name)
            continue
        target_c = _canonical(os.path.join(dest, name))
        if target_c != dest_c and not target_c.startswith(dest_c + os.sep):
            skipped.append(name)
            continue
        zf.extract(member, dest)
    return skipped


def safe_join(base: str, *parts: str) -> str:
    """Join *parts* onto *base*, refusing to return a path outside *base*.

    Raises ValueError when the joined path escapes *base* (e.g. via ``..``
    segments or an absolute part). Use for every filesystem path built from
    template-controlled strings.
    """
    joined = os.path.join(base, *parts)
    if not is_within_directory(base, joined):
        raise ValueError(f"Refusing path outside container: {joined!r}")
    return joined


def safe_glob(base: str, *parts: str) -> list[str]:
    """Glob a template-supplied relative pattern under *base*.

    The pattern itself must stay inside *base* (ValueError otherwise), and
    every match is re-checked after symlink resolution — matches that resolve
    outside *base* are dropped rather than acted on.
    """
    pattern = safe_join(base, *parts)
    base_c = _canonical(base)
    kept: list[str] = []
    for match in _glob.glob(pattern, recursive=True):
        resolved = _canonical(match)
        if resolved == base_c or resolved.startswith(base_c + os.sep):
            kept.append(match)
    return kept


def assert_device_path_safe(path: str) -> str:
    """Guard for device-side restore paths (POSIX): reject ``..`` segments.

    Raises ValueError when the restore path could escape the domain it is
    being restored to.
    """
    if ".." in path.replace("\\", "/").split("/"):
        raise ValueError(
            f"Refusing device path escaping its domain: {path!r}"
        )
    return path
