"""Targeted fetch of the device's live .GlobalPreferences.plist.

Liquid Glass Disable (Beta 1), G1 route: the HomeDomain
``.GlobalPreferences.plist`` payload must be built from the file the
connected device actually carries, never from a template. This module is
the fetch channel — a deliberate mirror of
``src/restore/posterboard_backup.py``'s targeted backup: a full backup
whose mid-stream filter keeps ONLY the one file (everything else the
device uploads is drained, never written to disk), then the file is
extracted from the backup manifest with the same
``extract_gp_base_plist`` helper the iOS 27 Phase 0 path uses.

Failure is honest and fatal to the caller: no device, a locked device, an
unreadable (e.g. encrypted) manifest or a missing file all raise
NuggetException — the apply pass treats that as "cancel the apply, write
nothing", never as "fall back to a guess".
"""

import os
import tempfile

from pymobiledevice3.services.mobilebackup2 import Mobilebackup2Service

from src.devicemanagement.session import lockdown_session
from src.exceptions.device_errors import (
    is_connection_error as _is_connection_error,
    is_device_locked_error as _is_device_locked_error,
)
from src.exceptions.nugget_exception import NuggetException
from src.restore.protective import (
    GP_BASE_DOMAIN, GP_BASE_RELATIVE_PATH, extract_backup_file,
    extract_gp_base_plist,
)
from src.utils.async_retry import async_retry
from src.utils.stall_watchdog import run_with_stall_watchdog

_GP_FILENAME = ".GlobalPreferences.plist"

_KEEP_NAMES = {
    "HomeDomain/" + GP_BASE_RELATIVE_PATH,
    GP_BASE_RELATIVE_PATH,
}


def _keep_gp_only(backup_file) -> bool:
    """Mid-stream filter: keep only the HomeDomain .GlobalPreferences.plist.

    Upload names arrive domain-qualified on iOS 26
    (``HomeDomain/Library/Preferences/.GlobalPreferences.plist``) and as a
    raw tree on iOS 27 (``/.b/<n>/Library/Preferences/...``); both are
    accepted, everything else is drained.
    """
    name = (backup_file.device_name or "").replace("\\", "/").lstrip("/")
    if name in _KEEP_NAMES:
        return True
    parts = name.split("/")
    return (len(parts) >= 3 and parts[-1] == _GP_FILENAME
            and "/".join(parts[-3:]) == GP_BASE_RELATIVE_PATH)


# --- Liquid Glass (Latest) three-file capture ------------------------------
# Same targeted-backup channel, widened to the three HomeDomain
# preference files the Latest payload merges into (src/tweaks/lg_latest.py).
_LATEST_REL_PATHS = (
    ("gp", GP_BASE_RELATIVE_PATH),
    ("swiftui", "Library/Preferences/com.apple.SwiftUI.plist"),
    ("springboard", "Library/Preferences/com.apple.springboard.plist"),
)


def _keep_latest_files(backup_file) -> bool:
    """Mid-stream filter: keep only the three Latest base files."""
    name = (backup_file.device_name or "").replace("\\", "/").lstrip("/")
    parts = name.split("/")
    if len(parts) < 3:
        return name in (rel for _key, rel in _LATEST_REL_PATHS)
    tail = "/".join(parts[-3:])
    return tail in (rel for _key, rel in _LATEST_REL_PATHS)


async def fetch_device_latest_bases(udid: str, update_label=lambda x: None,
                                    update_progress=lambda x: None) -> dict:
    """Back up ONLY the three Liquid Glass (Latest) base files.

    Returns ``{"gp": bytes|None, "swiftui": bytes|None,
    "springboard": bytes|None}`` — raw device bytes, or None when the
    device does not carry that file (the SwiftUI plist is created lazily
    by the system and may legitimately not exist yet). The caller parses
    and fails closed on an unusable .GlobalPreferences.plist, exactly
    like ``fetch_device_gp_plist``'s contract.
    """
    max_retries = 3

    def _on_retry(attempt: int, total: int, e: Exception, delay: float) -> None:
        if attempt < total:
            update_label(f"Connection lost, retrying in {delay}s... "
                         f"(attempt {attempt}/{max_retries})")

    async def _attempt() -> dict:
        with tempfile.TemporaryDirectory(prefix="workslop_lgd_latest_") as backup_dir:
            async with lockdown_session(udid) as service_provider:
                async with Mobilebackup2Service(service_provider) as backup_client:
                    try:
                        await run_with_stall_watchdog(
                            lambda tracking_cb: backup_client.backup(
                                full=True, backup_directory=backup_dir,
                                progress_callback=tracking_cb,
                                filter_callback=_keep_latest_files),
                            update_progress,
                            operation="backup",
                        )
                    except Exception as e:
                        if _is_device_locked_error(e):
                            raise NuggetException(
                                "Device locked during backup. Please unlock "
                                "your device, keep it awake (tap screen "
                                "periodically), and try again.")
                        raise
            update_label("Reading the device's preference files...")
            result = {}
            for key, rel_path in _LATEST_REL_PATHS:
                dest = os.path.join(backup_dir, f"latest_{key}.plist")
                extracted = extract_backup_file(
                    backup_dir, udid, GP_BASE_DOMAIN, rel_path, dest)
                if extracted and os.path.exists(extracted):
                    with open(extracted, "rb") as fh:
                        data = fh.read()
                    result[key] = data if data else None
                else:
                    result[key] = None
            return result

    return await async_retry(
        _attempt, max_retries, retry_if=_is_connection_error,
        exp_cap=15, on_retry=_on_retry)


async def fetch_device_gp_plist(udid: str, update_label=lambda x: None,
                                update_progress=lambda x: None) -> bytes:
    """Back up ONLY the .GlobalPreferences.plist and return its raw bytes.

    Raises NuggetException when the file cannot be obtained — the caller
    must cancel rather than write anything.
    """
    max_retries = 3

    def _on_retry(attempt: int, total: int, e: Exception, delay: float) -> None:
        if attempt < total:
            update_label(f"Connection lost, retrying in {delay}s... "
                         f"(attempt {attempt}/{max_retries})")

    async def _attempt() -> bytes:
        with tempfile.TemporaryDirectory(prefix="workslop_lgd_gp_") as backup_dir:
            async with lockdown_session(udid) as service_provider:
                async with Mobilebackup2Service(service_provider) as backup_client:
                    try:
                        await run_with_stall_watchdog(
                            lambda tracking_cb: backup_client.backup(
                                full=True, backup_directory=backup_dir,
                                progress_callback=tracking_cb,
                                filter_callback=_keep_gp_only),
                            update_progress,
                            operation="backup",
                        )
                    except Exception as e:
                        if _is_device_locked_error(e):
                            raise NuggetException(
                                "Device locked during backup. Please unlock "
                                "your device, keep it awake (tap screen "
                                "periodically), and try again.")
                        raise
            update_label("Reading the device's .GlobalPreferences.plist...")
            dest = os.path.join(backup_dir, "device_gp.plist")
            extracted = extract_gp_base_plist(backup_dir, udid, dest)
            if not extracted or not os.path.exists(extracted):
                raise NuggetException(
                    "Liquid Glass Disable (Beta 1): the device's "
                    ".GlobalPreferences.plist could not be read from the "
                    "backup (the backup may be encrypted). Nothing was "
                    "written.")
            with open(extracted, "rb") as fh:
                data = fh.read()
            if not data:
                raise NuggetException(
                    "Liquid Glass Disable (Beta 1): the device's "
                    ".GlobalPreferences.plist came back empty. Nothing was "
                    "written.")
            return data

    return await async_retry(
        _attempt, max_retries, retry_if=_is_connection_error,
        exp_cap=15, on_retry=_on_retry)
