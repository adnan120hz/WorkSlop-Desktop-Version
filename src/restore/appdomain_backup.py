"""Targeted per-app backup browsing (iMazing-style fallback).

When HouseArrest denies container access — App Store apps without File
Sharing — iMazing still shows the app's data by reading it out of a device
backup: every app's container is stored under the ``AppDomain-<bundle_id>``
domain. This module backs up ONLY that domain (everything else the device
uploads is drained mid-stream, never written to disk) and exposes a
Manifest.db-backed listing so the App Data page can browse and download it.

Read-only by design: writing back would require a restore pass, which is a
different (destructive) operation. The App Data page disables upload /
delete / rename / new-folder while in backup mode.
"""

import os
import shutil
import sqlite3
import tempfile

from pymobiledevice3.services.mobilebackup2 import Mobilebackup2Service

from src.devicemanagement.session import lockdown_session
from src.restore.protective import _domain_match
from src.exceptions.nugget_exception import NuggetException
from src.utils.async_retry import async_retry
from src.utils.stall_watchdog import run_with_stall_watchdog


def app_domain(bundle_id: str) -> str:
    """The backup domain holding ``bundle_id``'s container."""
    return f"AppDomain-{bundle_id}"


async def targeted_app_domain_backup(
    udid: str,
    bundle_id: str,
    update_label=lambda x: None,
    update_progress=lambda x: None,
) -> str:
    """Back up ONLY ``AppDomain-<bundle_id>`` and return the backup dir.

    The returned directory contains ``<udid>/Manifest.db`` plus the payload
    files; the caller owns it and must ``shutil.rmtree`` it when done. Only
    the one app's domain is kept — the filter drops every other file the
    device uploads mid-stream, so no photos, messages or settings ever touch
    the disk here.
    """
    from src.exceptions.device_errors import is_connection_error as _is_connection_error
    from src.exceptions.device_errors import is_device_locked_error as _is_device_locked_error

    domain = app_domain(bundle_id)
    backup_dir = tempfile.mkdtemp(prefix="workslop_appdata_")
    max_retries = 3

    def _on_retry(attempt: int, total: int, e: Exception, delay: float) -> None:
        if attempt < total:
            update_label(f"Connection lost, retrying in {delay}s... "
                         f"(attempt {attempt}/{total})")

    async def _attempt():
        async with lockdown_session(udid) as service_provider:
            async with Mobilebackup2Service(service_provider) as backup_client:
                def _app_only(backup_file):
                    device_name = backup_file.device_name or ""
                    return _domain_match(device_name, domain)

                try:
                    update_label(f"Backing up {bundle_id} (app data only)...")
                    await run_with_stall_watchdog(
                        lambda tracking_cb: backup_client.backup(
                            full=True, backup_directory=backup_dir,
                            progress_callback=tracking_cb,
                            filter_callback=_app_only),
                        update_progress,
                        operation="backup",
                    )
                except Exception as e:
                    if _is_device_locked_error(e):
                        raise NuggetException(
                            "Device locked during backup. Unlock your iPhone, "
                            "keep it awake, and try again.")
                    raise

    try:
        await async_retry(
            _attempt, max_retries, retry_if=_is_connection_error,
            exp_cap=15, on_retry=_on_retry)
    except Exception:
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise
    return backup_dir


def payload_path(backup_dir: str, udid: str, file_id: str) -> str:
    """On-disk path of a backed-up file payload."""
    return os.path.join(backup_dir, udid, file_id[:2], file_id)


def list_app_domain_files(backup_dir: str, udid: str, bundle_id: str) -> list[dict]:
    """List an app's files from a targeted backup's Manifest.db.

    Returns entries sorted for display: ``{"name", "relativePath", "is_dir",
    "fileID" (None for dirs), "size"}``. Directories are synthesized from
    file paths because Manifest.db usually only lists files. ``relativePath``
    is relative to the container root (``""`` == root).
    """
    domain = app_domain(bundle_id)
    db_path = os.path.join(backup_dir, udid, "Manifest.db")
    if not os.path.exists(db_path):
        raise NuggetException("Backup manifest not found — the backup may have failed.")

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT fileID, relativePath FROM Files "
            "WHERE domain = ? AND flags = 1 AND fileID IS NOT NULL",
            (domain,),
        ).fetchall()
    finally:
        conn.close()

    files: dict[str, str] = {}  # relativePath -> fileID
    for file_id, rel in rows:
        if not rel:
            continue
        rel = rel.replace("\\", "/").lstrip("/")
        files[rel] = file_id

    if not files:
        raise NuggetException(
            f"No app data found for {bundle_id} in the backup. "
            "The app may store nothing on-device, or the backup was empty.")

    # Synthesize the directory tree from file paths.
    dirs: set[str] = set()
    for rel in files:
        parts = rel.split("/")
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))

    def _children(path: str) -> list[dict]:
        prefix = f"{path}/" if path else ""
        seen: dict[str, dict] = {}
        for rel, file_id in files.items():
            if not rel.startswith(prefix):
                continue
            rest = rel[len(prefix):]
            if "/" in rest:
                name = rest.split("/", 1)[0]
                key = f"d:{name}"
                if key not in seen:
                    seen[key] = {
                        "name": name,
                        "relativePath": f"{prefix}{name}",
                        "is_dir": True,
                        "fileID": None,
                        "size": 0,
                    }
            else:
                key = f"f:{rest}"
                if key not in seen:
                    try:
                        size = os.path.getsize(payload_path(backup_dir, udid, file_id))
                    except OSError:
                        size = 0
                    seen[key] = {
                        "name": rest,
                        "relativePath": rel,
                        "is_dir": False,
                        "fileID": file_id,
                        "size": size,
                    }
        entries = sorted(seen.values(),
                         key=lambda e: (not e["is_dir"], e["name"].lower()))
        return entries

    # Return a browser object: root listing + a lookup for any subpath.
    return _AppDomainTree(_children)


class _AppDomainTree:
    """Lazy tree view over the flat Manifest.db file list."""

    def __init__(self, children_fn):
        self._children_fn = children_fn

    def children(self, path: str) -> list[dict]:
        return self._children_fn(path or "")
