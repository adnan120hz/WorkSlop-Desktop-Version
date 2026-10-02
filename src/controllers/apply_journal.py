"""Durable per-tweak Apply Journal (Wave 10).

Every apply/reset operation produces one JSON document recording what was
requested, what was skipped and why, what was staged, and whether the
restore call delivered it. This is an audit record only:

* It is deliberately separate from ``src/restore/lastapply.py`` —
  ``lastapply.json`` stays the sparse-restore skip optimization keyed by
  ``"{domain}/{restore_path}" -> sha1(contents)`` and is never read here.
* The restore path never reads the journal to decide anything.
* ``delivered-by-restore`` means the restore call completed. It does NOT
  mean SpringBoard rendered the change or that a tweak is device-proven.
* Passwords, tokens, and credentials are never accepted by this API;
  values pass through :func:`value_summary`, which hashes anything long,
  structured, or user-entered instead of storing it raw.

Storage: ``<log dir>/ApplyJournal/apply-<uuid>.json`` /
``reset-<uuid>.json`` (the log dir comes from
``src/controllers/nugget_logger.py::get_log_dir()``). Writes are atomic
(serialize to ``<name>.json.tmp`` in the same directory, then
``os.replace()``) and the newest 100 files per prefix are retained.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

log = logging.getLogger("WorkSlop.apply_journal")

SCHEMA_VERSION = 1

# Operation statuses (exhaustive).
OP_SUCCESS = "success"
OP_PARTIAL = "partial"
OP_FAILED = "failed"
OP_ABORTED = "aborted"

# Per-tweak statuses (exhaustive). No other transitions are allowed:
#   requested -> staged -> delivered-by-restore (restore returned)
#   requested -> staged -> not-delivered        (restore raised)
#   requested -> skipped                        (gate/HotLoad/compat)
#   requested -> failed                         (generation raised / nothing staged)
TW_REQUESTED = "requested"
TW_STAGED = "staged"
TW_SKIPPED = "skipped"
TW_FAILED = "failed"
TW_DELIVERED = "delivered-by-restore"
TW_NOT_DELIVERED = "not-delivered"

_JOURNAL_PREFIX = {"apply": "apply", "reset": "reset"}
RETENTION_PER_PREFIX = 100

_TEXT_LIMIT = 80


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def value_summary(value, *, sensitive: bool = False):
    """Summarize a tweak value for the journal (the only summarizer).

    bool / int / float / None are stored as-is. Short strings are stored
    as-is unless *sensitive* (text-input tweaks and Status Bar text fields
    are always summarized — they are user-entered text). Everything else
    becomes ``{"type", "length", "sha256"}``; dicts also carry their sorted
    key names, never nested values.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        if not sensitive and len(value) <= _TEXT_LIMIT:
            return value
        data = value.encode("utf-8", "replace")
        return {"type": "str", "length": len(value),
                "sha256": hashlib.sha256(data).hexdigest()}
    if isinstance(value, (bytes, bytearray)):
        data = bytes(value)
        return {"type": "bytes", "length": len(data),
                "sha256": hashlib.sha256(data).hexdigest()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        digest = hashlib.sha256()
        for item in items:
            digest.update(repr(item).encode("utf-8", "replace"))
        return {"type": "list", "length": len(items),
                "sha256": digest.hexdigest()}
    if isinstance(value, dict):
        digest = hashlib.sha256()
        for key in sorted(value, key=repr):
            digest.update(repr(key).encode("utf-8", "replace"))
        return {"type": "dict", "length": len(value),
                "keys": sorted(str(k) for k in value.keys()),
                "sha256": digest.hexdigest()}
    text = repr(value)
    return {"type": type(value).__name__, "length": len(text),
            "sha256": hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()}


def file_key(domain: str, path: str) -> str:
    """The ``"{domain}/{path}"`` reference shape (same as sparse_signature)."""
    return f"{domain}/{(path or '').lstrip('/')}"


def build_file_record(file_obj) -> dict:
    """Build one top-level journal file record from a FileToRestore-like
    object (fields are read, never a new restore object)."""
    domain = getattr(file_obj, "domain", "") or ""
    path = getattr(file_obj, "restore_path", None)
    if path is None:
        path = getattr(file_obj, "path", "") or ""
    path = str(path).lstrip("/")
    record = {
        "domain": domain,
        "path": path,
        "size": None,
        "sha1": None,
        "owner": getattr(file_obj, "owner", None),
        "group": getattr(file_obj, "group", None),
    }
    data = getattr(file_obj, "contents", None)
    if data is None:
        src = getattr(file_obj, "contents_path", None)
        if src:
            try:
                with open(src, "rb") as fh:
                    data = fh.read()
            except OSError as e:
                record["error"] = f"{type(e).__name__}: {e}"
                return record
    if data is not None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        record["size"] = len(data)
        record["sha1"] = hashlib.sha1(data).hexdigest()
    return record


def default_journal_dir() -> str:
    override = os.environ.get("WORKSLOP_APPLY_JOURNAL_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    from src.controllers.nugget_logger import get_log_dir
    journal_dir = os.path.join(get_log_dir(), "ApplyJournal")
    os.makedirs(journal_dir, exist_ok=True)
    return journal_dir


class ApplyJournal:
    """One operation's journal document. Re-written at begin, after
    staging, and at finalize so a crash mid-apply leaves the last
    consistent state on disk."""

    def __init__(self, mode: str, device: dict | None = None,
                 journal_dir: str | None = None):
        if mode not in _JOURNAL_PREFIX:
            raise ValueError(f"unknown journal mode: {mode!r}")
        from src.version import App_Version, App_Build
        self.mode = mode
        self.operation_id = uuid.uuid4().hex
        self._started = time.monotonic()
        self.data = {
            "schema_version": SCHEMA_VERSION,
            "operation_id": self.operation_id,
            "mode": mode,
            "started_at": _utc_now(),
            "ended_at": None,
            "duration_ms": None,
            "app": {"version": App_Version, "build": App_Build},
            "device": {
                "name": (device or {}).get("name") or "",
                "model": (device or {}).get("model") or "",
                "ios": (device or {}).get("ios") or "",
                "build": (device or {}).get("build") or "",
                "udid": (device or {}).get("udid") or "",
            },
            "status": None,
            "error": None,
            "restore_file_count": 0,
            "files": [],
            "tweaks": [],
        }
        self._dir = journal_dir or default_journal_dir()
        os.makedirs(self._dir, exist_ok=True)
        self.path = os.path.join(
            self._dir, f"{_JOURNAL_PREFIX[mode]}-{self.operation_id}.json")
        self._file_keys: list[str] = []
        self.finalized = False

    # -- entries ---------------------------------------------------------
    def add_entry(self, entry: dict) -> dict:
        entry.setdefault("status", TW_REQUESTED)
        entry.setdefault("requested", True)
        entry.setdefault("skip_reason", None)
        entry.setdefault("files", [])
        entry.setdefault("error", None)
        self.data["tweaks"].append(entry)
        return entry

    def entries_for(self, tweak_id_name: str) -> list:
        return [e for e in self.data["tweaks"]
                if e.get("tweak_id") == tweak_id_name]

    # -- files ------------------------------------------------------------
    def attach_files(self, files) -> list:
        """Build the top-level file records from the staged file list
        (excludes nothing — unlike sparse_signature) and return the
        ``"{domain}/{path}"`` keys in the same order."""
        records = [build_file_record(f) for f in files]
        self.data["files"] = records
        self.data["restore_file_count"] = len(records)
        self._file_keys = [file_key(r["domain"], r["path"]) for r in records]
        return list(self._file_keys)

    def associate(self, entry: dict, file_keys) -> None:
        """Reference staged files (by key) on a per-tweak entry."""
        for key in file_keys:
            if key not in entry["files"]:
                entry["files"].append(key)

    def key_for_index(self, index: int):
        if 0 <= index < len(self._file_keys):
            return self._file_keys[index]
        return None

    # -- lifecycle --------------------------------------------------------
    def write(self) -> str:
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, sort_keys=False)
        os.replace(tmp_path, self.path)
        return self.path

    def finalize(self, status: str, error: str | None = None) -> str:
        self.data["status"] = status
        self.data["error"] = error
        self.data["ended_at"] = _utc_now()
        self.data["duration_ms"] = int(
            (time.monotonic() - self._started) * 1000)
        self.finalized = True
        path = self.write()
        self._prune()
        return path

    def _prune(self) -> None:
        prefix = _JOURNAL_PREFIX[self.mode] + "-"
        try:
            names = [n for n in os.listdir(self._dir)
                     if n.startswith(prefix) and n.endswith(".json")]
        except OSError:
            return
        names.sort(key=lambda n: os.path.getmtime(
            os.path.join(self._dir, n)), reverse=True)
        for name in names[RETENTION_PER_PREFIX:]:
            try:
                os.remove(os.path.join(self._dir, name))
            except OSError:
                pass


def begin_journal(mode: str, device: dict | None = None,
                  journal_dir: str | None = None) -> ApplyJournal:
    """Create and write the begin state of a new operation journal."""
    journal = ApplyJournal(mode, device=device, journal_dir=journal_dir)
    journal.write()
    return journal
