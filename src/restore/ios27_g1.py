"""iOS 27 apply route: the device-proven G1 truck.

Pipeline (user order 2026-10-11): full backup of ALL device data to this
computer -> build a payload adapted to the tweaks the user enabled ->
modify (inject the payload into the backup) -> full restore of the
backup. No wipe, no sparse-restore phase, no selective/drained backup:
the backup taken here IS the user's data protection.

Watchdog: the whole route is bounded by ``WATCHDOG_SECONDS`` (12
minutes), counted from the moment the backup begins. A new phase is
never STARTED after the deadline; the backup itself is aborted on
expiry (it writes nothing to the device, so aborting it is safe). A
restore already in flight is NEVER interrupted — cutting a restore
mid-flight is exactly the unsafe action this watchdog exists to
prevent; if the deadline passes during the restore it completes and
the timeout is reported honestly in the final alert.

Eligibility: iOS 27.0 Developer Beta 1-9, 27.0 RC, 27.0 official
stable, and 27.0.1 only. Anything else (other 27.x, non-26.x below
27) is rejected with "Not supported" before anything runs. Beta/RC
builds report ProductVersion "27.0" over the cable, so the version
gate covers every 27.0 variant including dev beta 9 (whose build
number is not in our verified list); the build allowlist gives
build-level precision for the user-verified 27.0 builds.

The payload is NOT hardcoded: it is built from the staged
``FileToRestore`` list the normal tweak pass produced, so every
enabled tweak contributes its own target files (multi-tweak
adaptation is structural, not a special case). The per-tweak -> file
attribution is derived from the Apply Journal entries (registry spec
``location`` joined to the payload's (domain, path)), never from a
hardcoded file list.

The iOS 26 partial-restore route is untouched by this module.
"""

import asyncio
import hashlib
import os
import time
from pathlib import Path

from packaging.version import Version
from PySide6.QtCore import QCoreApplication

from src.exceptions.nugget_exception import NuggetException
from src.utils.log_util import log_error, log_info, log_warn


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------

#: 12-minute total watchdog, counted from the start of the full backup.
WATCHDOG_SECONDS = 12 * 60

#: iOS 27.0 builds verified by the user (2026-09-30): dev betas 1-8,
#: then the 27.0 RC + official stable. Dev beta 9's build number is not
#: in the verified list — it is covered by the "27.0" version gate
#: below (all 27.0 variants report ProductVersion "27.0" over the cable).
IOS27_G1_SUPPORTED_BUILDS = frozenset({
    "24A5355q", "24A5370h", "24A5380h", "24A5390f",
    "24A5408d", "24A5418b", "24A5424a", "24A5430a",
    "24A435", "24A437",
})

#: Supported ProductVersion values. "27.0" covers Developer Beta 1-9,
#: the RC, and the official stable (all report "27.0"); "27.0.1" is the
#: only other supported release.
IOS27_G1_SUPPORTED_VERSIONS = (Version("27.0"), Version("27.0.1"))

NOT_SUPPORTED_MESSAGE = (
    "Not supported: this device runs an iOS version outside the "
    "supported list (iOS 27.0 Developer Beta 1-9, 27.0 RC, 27.0 "
    "official, 27.0.1). Nothing was applied."
)


def is_ios27_g1_supported(version, build) -> bool:
    """True only for the supported iOS 27 set (see module docstring)."""
    try:
        parsed = Version(str(version or ""))
    except Exception:
        parsed = None
    if parsed is not None and parsed in IOS27_G1_SUPPORTED_VERSIONS:
        return True
    if str(build or "") in IOS27_G1_SUPPORTED_BUILDS:
        return True
    return False


# ---------------------------------------------------------------------------
# Pre-apply warning (English, blunt; shown and confirmed before the route)
# ---------------------------------------------------------------------------

IOS27_WARNING_TITLE = "iOS 27 — Risk Warning"

IOS27_WARNING_TEXT = (
    "WARNING: applying tweaks on iOS 27 is experimental and risky.\n\n"
    "iOS 27 can put your iPhone into a BOOTLOOP (the phone gets stuck "
    "on the Apple logo and will not start). A full backup of ALL your "
    "data is taken to this computer before anything is written, but a "
    "backup cannot undo every kind of damage.\n\n"
    "The owner of this software (Adnan.120hz) is NOT responsible for "
    "any damage, bootloop, or data loss caused by using it on iOS 27.\n\n"
    "Your device backup must NOT be encrypted for this route "
    "(Finder/iTunes: uncheck 'Encrypt local backup'), otherwise the "
    "apply is refused before anything is written.\n\n"
    "Press Resume ONLY if you have a backup and accept the full risk. "
    "Press Abort to stop now — nothing will be written."
)


# ---------------------------------------------------------------------------
# Watchdog
# ---------------------------------------------------------------------------

class G1WatchdogExpired(NuggetException):
    """Raised when the 12-minute iOS 27 route deadline is hit."""


class G1Watchdog:
    """Total-time watchdog for the iOS 27 G1 route.

    The clock starts when the full backup begins. ``check()`` raises
    :class:`G1WatchdogExpired` past the deadline; callers check at
    every phase boundary and inside long-running progress callbacks.
    """

    def __init__(self, total_seconds: float = WATCHDOG_SECONDS):
        self.total_seconds = float(total_seconds)
        self.started_at = time.monotonic()
        self.deadline = self.started_at + self.total_seconds
        self.expired_once = False

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def check(self, phase: str = "") -> None:
        if time.monotonic() > self.deadline:
            self.expired_once = True
            base = QCoreApplication.translate(
                "Nugget",
                "iOS 27 apply timed out: the 12-minute safety limit was "
                "reached. The operation was stopped before any further "
                "step could start. If the backup had already finished it "
                "is kept on this computer; your device was not left "
                "half-written.")
            if phase:
                # phase name is developer-facing; appended outside the
                # translatable string (no f-string inside translate).
                base += " [phase: " + str(phase) + "]"
            raise G1WatchdogExpired(base)


# ---------------------------------------------------------------------------
# Payload planning (pure, unit-tested)
# ---------------------------------------------------------------------------

_FILE_MODE = 0o100644  # S_IFREG | 0644, as the LGD injection batch uses


def _coerce_bytes(contents) -> bytes:
    if isinstance(contents, str):
        return contents.encode("utf-8")
    if contents is None:
        return b""
    return bytes(contents)


def _try_parse_plist_dict(data: bytes):
    """Parse ``data`` as a plist; return the dict, or None."""
    try:
        import plistlib as _plistlib
        parsed = _plistlib.loads(bytes(data))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def plan_g1_payloads(files_to_restore, backup_root=None, udid=None):
    """Build the G1 injection payload from the staged FileToRestore list.

    Every enabled tweak already contributed its target files to
    ``files_to_restore`` via the normal tweak pass — this function only
    translates them into ``(domain, rel_path, bytes, mode, owner,
    group)`` injection tuples and records a per-file audit manifest.
    Files that cannot ride a backup manifest (empty domain, or
    directory-only records) are SKIPPED with an audit note, never
    silently dropped.

    When ``backup_root``/``udid`` are given, each plist-dict payload is
    merged onto the file already in the backup ("pulled from the
    backup and modified"): pre-existing keys the user (or a previous
    apply) put there are never dropped by a whole-file replace; the
    staged tweak keys win for their own keys. Files absent from the
    backup, or payloads that are not plist dicts, are injected as new
    files, byte-identical to what staging produced.

    Returns ``(payloads, skipped, manifest)`` where ``manifest`` is a
    list of ``{"domain", "rel_path", "size", "owner", "group",
    "contents_kind", "merged"}`` dicts in the same order as
    ``payloads``.
    """
    import plistlib as _plistlib
    import tempfile as _tempfile

    payloads = []
    skipped = []
    manifest = []
    merge_base = None
    if backup_root is not None and udid is not None:
        from src.restore.protective import extract_backup_file
        merge_base = (backup_root, udid, extract_backup_file)

    for f in files_to_restore or []:
        domain = getattr(f, "domain", "") or ""
        rel_path = getattr(f, "restore_path", "") or ""
        if not domain:
            skipped.append({
                "rel_path": rel_path,
                "reason": "empty domain — cannot be injected into a backup manifest",
            })
            log_warn(f"iOS27-G1: skipping file with empty domain: {rel_path!r}")
            continue
        if getattr(f, "is_dir", False):
            skipped.append({
                "rel_path": rel_path,
                "reason": "directory-only record — not a file payload",
            })
            continue
        contents = _coerce_bytes(getattr(f, "contents", b""))
        mode = getattr(f, "mode", None) or _FILE_MODE
        owner = int(getattr(f, "owner", 501) or 501)
        group = int(getattr(f, "group", 501) or 501)
        merged = False
        # Merge onto the backup's own copy when both sides are plist
        # dicts: never drop keys that are already on the device.
        staged_dict = _try_parse_plist_dict(contents)
        if staged_dict is not None and merge_base is not None:
            _root, _udid, _extract = merge_base
            try:
                with _tempfile.TemporaryDirectory(
                        prefix="workslop_ios27_g1_merge_") as tmp:
                    dest = os.path.join(tmp, "base.plist")
                    pulled = _extract(_root, _udid, domain, rel_path, dest)
                    if pulled and os.path.exists(pulled):
                        with open(pulled, "rb") as fh:
                            existing = _try_parse_plist_dict(fh.read())
                        if isinstance(existing, dict):
                            final = dict(existing)
                            final.update(staged_dict)
                            contents = _plistlib.dumps(
                                final, fmt=_plistlib.FMT_BINARY, sort_keys=True)
                            merged = True
                            log_info(
                                f"iOS27-G1: merged {len(staged_dict)} staged key(s) "
                                f"onto the backup's {domain}/{rel_path} "
                                f"({len(existing)} existing key(s) kept)")
            except Exception as e:
                log_warn(f"iOS27-G1: merge skipped for {domain}/{rel_path} "
                         f"({type(e).__name__}: {e}); staged file used as-is")
        payloads.append((domain, rel_path, contents, mode, owner, group))
        manifest.append({
            "domain": domain,
            "rel_path": rel_path,
            "size": len(contents),
            "owner": owner,
            "group": group,
            "contents_kind": "plist" if contents.lstrip().startswith(b"bplist")
                             or contents.lstrip().startswith(b"<?xml") else "binary",
            "merged": merged,
        })
    return payloads, skipped, manifest


def attribute_payloads_to_tweaks(payloads, journal_entries):
    """Attribute each payload file to the tweaks that staged it.

    The join key is the registry spec ``location`` (the full device
    path, e.g. ``/var/Managed Preferences/mobile/com.apple.UIKit.plist``)
    found on Apply Journal entries, mapped to ``(domain, rel_path)``
    with the same ``split_path_into_domain`` the staging used. Payloads
    with no matching entry are attributed to ``"<staging>"`` (PosterBoard,
    skip-setup, status-bar, passcode and other non-registry families)
    rather than invented.

    ``journal_entries``: iterable of dicts with ``tweak_id`` and
    ``operation`` (``{"location": <path>, ...}``). Returns a list of
    ``{"domain", "rel_path", "tweaks": [tweak_id, ...]}`` in payload
    order.
    """
    from src.restore.path_mapping import split_path_into_domain

    location_to_tweaks = {}
    for entry in journal_entries or []:
        op = (entry or {}).get("operation") or {}
        loc = op.get("location")
        if not loc:
            continue
        try:
            domain, rel = split_path_into_domain(str(loc))
        except Exception:
            continue
        if not domain:
            continue
        key = (domain, rel)
        tid = (entry or {}).get("tweak_id") or (entry or {}).get("id") or "?"
        location_to_tweaks.setdefault(key, [])
        if tid not in location_to_tweaks[key]:
            location_to_tweaks[key].append(tid)

    attributed = []
    for p in payloads:
        domain, rel_path = p[0], p[1]
        tweaks = location_to_tweaks.get((domain, rel_path), ["<staging>"])
        attributed.append({
            "domain": domain,
            "rel_path": rel_path,
            "tweaks": list(tweaks),
        })
    return attributed


# ---------------------------------------------------------------------------
# Backup pool (dedicated; never the iOS 27 protective-backup pool)
# ---------------------------------------------------------------------------

def ios27_g1_backup_base(udid: str) -> Path:
    from src.restore.protective import protective_persistent_base
    safe = "".join(c for c in str(udid or "unknown") if c.isalnum() or c in "._-")
    return protective_persistent_base() / f"{safe}-ios27-g1"


def new_ios27_g1_backup_dir(udid: str) -> str:
    """Fresh backup root: <pool>/<ts>-<pid>-<rand>/device_backup."""
    import uuid as _uuid
    run_dir = (ios27_g1_backup_base(udid)
               / f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{_uuid.uuid4().hex[:8]}")
    backup_root = run_dir / "device_backup"
    backup_root.mkdir(parents=True, exist_ok=True)
    return str(backup_root)


def prune_ios27_g1_backups(udid: str, keep: int = 2) -> int:
    """Keep only the newest ``keep`` completed runs; drop stale ones."""
    import shutil
    base = ios27_g1_backup_base(udid)
    if not base.is_dir():
        return 0
    now = time.time()
    removed = 0
    entries = [e for e in base.iterdir() if e.is_dir()]

    def _complete(run_dir: Path) -> bool:
        for candidate in (run_dir / "device_backup" / str(udid),
                          run_dir / "device_backup"):
            if (candidate / "Manifest.db").is_file():
                return True
        return False

    runs = [e for e in entries if _complete(e)]
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for old in runs[max(keep, 0):]:
        shutil.rmtree(old, ignore_errors=True)
        if not old.exists():
            removed += 1
    for stale in (e for e in entries if e not in runs):
        try:
            age = now - stale.stat().st_mtime
        except OSError:
            continue
        if age > 7 * 24 * 3600:  # a week; may be an interrupted run
            shutil.rmtree(stale, ignore_errors=True)
            if not stale.exists():
                removed += 1
    return removed


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------

def _device_dir_for(backup_root, udid) -> Path:
    candidate = Path(backup_root) / str(udid)
    if candidate.is_dir():
        return candidate
    return Path(backup_root)


async def backup_ios27_full(udid: str, *,
                            update_label=lambda x: None,
                            backup_progress=lambda x: None,
                            watchdog: "G1Watchdog" = None) -> str:
    """Phase A: full backup of ALL device data to this computer.

    The watchdog clock starts here (it is created if not given).
    Encrypted backups are refused honestly. Returns the backup root.
    """
    from src.devicemanagement.session import lockdown_session
    from src.restore.inject import _is_encrypted_backup
    from src.restore.protective import check_disk_space_for_backup
    from src.restore.restore import _start_mobilebackup2
    from src.utils.stall_watchdog import run_with_stall_watchdog

    if watchdog is None:
        watchdog = G1Watchdog()
    prune_ios27_g1_backups(udid, keep=1)
    backup_root = new_ios27_g1_backup_dir(udid)
    log_info(f"iOS27-G1: backup root {backup_root} "
             f"(watchdog {watchdog.total_seconds / 60:.0f} min)")

    update_label(QCoreApplication.translate(
        "Nugget",
        "iOS 27: starting FULL backup of your device (all data)...\n"
        "Do not unplug your device."))
    watchdog.check("backup")

    def _backup_cb(value):
        # Aborting mid-backup is safe: nothing has been written to the
        # device yet. This is the only long-running phase the watchdog
        # may interrupt.
        watchdog.check("backup")
        backup_progress(value)

    async with lockdown_session(udid) as lc:
        await check_disk_space_for_backup(lc, path=backup_root)
        async with _start_mobilebackup2(lc) as mb:
            try:
                will_encrypt = await mb.get_will_encrypt()
            except Exception:
                will_encrypt = False
            if will_encrypt:
                raise NuggetException(QCoreApplication.translate(
                    "Nugget",
                    "iOS 27 apply: your device backup is encrypted, and "
                    "this route cannot write into an encrypted backup "
                    "safely. Turn off backup encryption (Finder/iTunes: "
                    "uncheck 'Encrypt local backup'), then try again. "
                    "Nothing was written; your device was not changed."))
            await run_with_stall_watchdog(
                lambda tracking_cb: mb.backup(
                    full=True, backup_directory=backup_root,
                    progress_callback=tracking_cb),
                _backup_cb,
                operation="backup",
            )
    device_dir = _device_dir_for(backup_root, udid)
    if not (device_dir / "Manifest.db").is_file():
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "iOS 27 apply: the full backup did not produce a usable "
            "backup, so nothing was restored. Your device was not "
            "changed."))
    if _is_encrypted_backup(device_dir):
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "iOS 27 apply: the backup came back encrypted, so the "
            "payload cannot be written into it safely. Nothing was "
            "restored; your device was not changed."))
    return backup_root


async def deliver_ios27_payload(backup_root: str, udid: str, payloads: list, *,
                                update_label=lambda x: None,
                                restore_progress=lambda x: None,
                                watchdog: "G1Watchdog" = None,
                                reboot: bool = False) -> tuple:
    """Phases B-D: verify backup, inject payload, verify, full restore.

    ``payloads``: list of ``(domain, rel_path, bytes, mode, owner,
    group)`` from :func:`plan_g1_payloads`. Nothing is written to the
    device before the final restore. Returns the backup root.

    The watchdog deadline gates STARTING the restore; a restore
    already in flight is never interrupted (cutting it mid-flight is
    the unsafe action). Returns ``(backup_root, timed_out)`` where
    ``timed_out`` is True when the restore finished past the deadline
    (reported honestly by the caller).
    """
    from src.devicemanagement.session import lockdown_session
    from src.restore.inject import inject_files_into_backup
    from src.restore.protective import verify_backup_payloads
    from src.restore.restore import _restore_protective_backup

    if watchdog is None:
        watchdog = G1Watchdog()
    timed_out_during_restore = False

    if not payloads:
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "iOS 27 apply: there is nothing to deliver (no tweak files "
            "were staged). Nothing was written."))

    # ---- Phase B/C: verify backup complete, then inject the payload ----
    watchdog.check("payload injection")
    update_label(QCoreApplication.translate(
        "Nugget", "iOS 27: verifying the backup, then writing the payload..."))
    missing = verify_backup_payloads(backup_root, udid)
    if missing:
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "iOS 27 apply: the full backup is incomplete (%1 manifest "
            "file(s) have no data), so nothing was restored. Your "
            "device was not changed. The incomplete backup is kept on "
            "this computer for inspection.").replace("%1", str(len(missing))))

    injected, unchanged, failed = await asyncio.to_thread(
        inject_files_into_backup, backup_root, udid, payloads)
    if failed or injected + unchanged != len(payloads):
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "iOS 27 apply: the payload could not be written into the "
            "backup (%1 of %2 file(s) failed), so nothing was restored. "
            "Your device was not changed.").replace("%1", str(failed)).replace(
                "%2", str(len(payloads))))

    # Re-read the injected files from disk and confirm every payload
    # landed byte-identical before the restore is allowed to start.
    watchdog.check("payload verification")
    problems = _verify_injected_files(backup_root, udid, payloads)
    if problems:
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "iOS 27 apply: the verification gate failed, so nothing was "
            "restored and your device was not changed:\n")
            + "\n".join(f"\u2022 {p}" for p in problems))

    # ---- Phase D: full restore -----------------------------------------
    try:
        watchdog.check("restore")
    except G1WatchdogExpired:
        raise G1WatchdogExpired(QCoreApplication.translate(
            "Nugget",
            "iOS 27 apply timed out: the 12-minute safety limit was "
            "reached after the payload was written into the backup but "
            "before the restore started. NOTHING was written to your "
            "device. The complete backup (with your tweaks staged inside) "
            "is kept at:\n%1").replace("%1", str(backup_root)))
    update_label(QCoreApplication.translate(
        "Nugget", "iOS 27: restoring the full backup to your device...\n"
        "Do not unplug your device."))

    def _restore_cb(value):
        # Heartbeat only: the restore is never cancelled by the
        # watchdog (see module docstring). Flag the overrun so the
        # final alert reports it honestly.
        nonlocal timed_out_during_restore
        if time.monotonic() > watchdog.deadline:
            timed_out_during_restore = True
        restore_progress(value)

    async with lockdown_session(udid) as lc:
        await _restore_protective_backup(
            lc, backup_root, udid, reboot=False,
            progress_callback=_restore_cb, backup_password="")
        if reboot:
            from src.restore import reboot_device
            await reboot_device(True, lc)

    if timed_out_during_restore:
        log_warn("iOS27-G1: restore finished past the 12-minute deadline; "
                 "reporting honestly in the final alert.")
    return backup_root, timed_out_during_restore


async def run_ios27_g1_route(udid: str, payloads: list, *,
                             update_label=lambda x: None,
                             backup_progress=lambda x: None,
                             restore_progress=lambda x: None,
                             watchdog_seconds: float = WATCHDOG_SECONDS,
                             version: str = "", build: str = "",
                             reboot: bool = False) -> str:
    """Full backup (all data) -> inject payload -> verify -> full restore.

    Convenience wrapper over :func:`backup_ios27_full` +
    :func:`deliver_ios27_payload` for callers that do not need the
    backup in between. Returns the backup root used.
    """
    watchdog = G1Watchdog(total_seconds=watchdog_seconds)
    backup_root = await backup_ios27_full(
        udid, update_label=update_label,
        backup_progress=backup_progress, watchdog=watchdog)
    backup_root, _timed_out = await deliver_ios27_payload(
        backup_root, udid, payloads, update_label=update_label,
        restore_progress=restore_progress, watchdog=watchdog,
        reboot=reboot)
    return backup_root


def _verify_injected_files(backup_root, udid, payloads) -> list:
    """Re-read every payload from the backup and confirm byte equality.

    Returns a list of problem strings (empty = all good).
    """
    problems = []
    for domain, rel_path, data, _mode, _owner, _group in payloads:
        file_id = hashlib.sha1(
            f"{domain}-{rel_path}".encode("utf-8")).hexdigest()
        disk_path = _device_dir_for(backup_root, udid) / file_id[:2] / file_id
        if not disk_path.is_file():
            problems.append(f"{domain}/{rel_path}: not found in backup after injection")
            continue
        try:
            on_disk = disk_path.read_bytes()
        except OSError as e:
            problems.append(f"{domain}/{rel_path}: unreadable after injection ({e})")
            continue
        if on_disk != bytes(data):
            problems.append(
                f"{domain}/{rel_path}: content mismatch after injection "
                f"(expected {len(data)} bytes, found {len(on_disk)})")
    return problems
