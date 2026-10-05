"""Liquid Glass Disable (Beta 1) — full-backup delivery route (iOS 26.6.x).

On iOS 26.6.x builds 23G82/23G83 the G1/G2 payloads can ride a true full
backup instead of the sparse (partial) restore: take a complete,
unfiltered device backup, inject the payload files into that backup,
verify the result with HARD gates, then restore the backup with the
same retry/watchdog-wrapped native restore the iOS 27 protective flow
uses (``_restore_protective_backup``).

Why a separate route: field reports (beta testers, 2026-10-05) showed
the sparse G2 overlay producing no visible change, and community intel
(nxtcoreee3) holds that the working private method writes the global
preferences file through a full restore. This module does NOT claim the
payload key is read by iOS 26.6.1 — it only changes the delivery
channel, reusing the same verified payloads (``src/tweaks/lg_disable.py``)
and the same fail-hard verification.

Safety contract (every failure BEFORE the restore leaves the device
completely untouched):

* exact gate: iOS 26.6.x AND build 23G82/23G83 — nothing else enters;
* disk space sized to the device is checked before the backup starts;
* the finished backup must be structurally complete (every manifest
  row has its payload) or the route aborts;
* an encrypted backup aborts the route honestly (plaintext injection
  into an encrypted manifest would corrupt the restore) — there is NO
  silent fallback to another channel;
* injection must account for every file (injected or byte-identical),
  and the injected payloads are re-read from disk and re-verified
  (parse, real-bool candidate key, G1 diff vs. the original file
  extracted from THIS backup) before the restore begins;
* the pristine device original from this backup is saved for rollback
  (first capture wins) before anything is written.

The restore itself never erases the device: it is a normal
mobilebackup2 restore of a complete backup, followed by a reboot only
when the caller asks for one.
"""

import asyncio
import hashlib
import os
import plistlib
import tempfile
from pathlib import Path
from typing import Optional

from packaging.version import Version
from PySide6.QtCore import QCoreApplication

from src.exceptions.nugget_exception import NuggetException
from src.tweaks import lg_disable

# Exact applicability window for this route. 23G82 is iOS 26.6.1 RC,
# 23G83 is iOS 26.6.1 final; both report version 26.6.1.
LGD_FULL_MIN_VERSION = Version("26.6")
LGD_FULL_MAX_VERSION = Version("26.7")
LGD_FULL_BUILDS = frozenset({"23G82", "23G83"})

_FILE_MODE = 0o100644  # S_IFREG | 0644, as the Phase 1 injection batch uses
_OWNER = 501


def lgd_full_route_applicable(version, build) -> bool:
    """True only inside the exact 26.6.x / 23G82|23G83 window."""
    try:
        parsed = Version(str(version or ""))
    except Exception:
        return False
    return (LGD_FULL_MIN_VERSION <= parsed < LGD_FULL_MAX_VERSION
            and str(build or "") in LGD_FULL_BUILDS)


# --- payload planning (pure, unit-tested) ---------------------------------

def _inject_tuple(domain: str, rel_path: str, data: bytes):
    return (domain, rel_path, bytes(data), _FILE_MODE, _OWNER, _OWNER)


def plan_apply_payloads(*, g1_active: bool, g2_active: bool,
                        g1_base: Optional[dict]) -> list:
    """Inject tuples for an apply. G1 refuses to plan without its base."""
    payloads = []
    if g2_active:
        payloads.append(_inject_tuple(
            lg_disable.G2_DOMAIN, lg_disable.G2_REL_PATH,
            lg_disable.build_g2_payload(
                {lg_disable.GP_KEY: lg_disable.GP_KEY_VALUE})))
    if g1_active:
        if not isinstance(g1_base, dict):
            raise NuggetException(QCoreApplication.translate(
                "Nugget",
                "Liquid Glass Disable (Beta 1): the full-backup route "
                "needs the device's own .GlobalPreferences.plist as the "
                "G1 merge base, and it could not be read. Nothing was "
                "written."))
        payloads.append(_inject_tuple(
            lg_disable.G1_DOMAIN, lg_disable.G1_REL_PATH,
            lg_disable.build_g1_payload(
                g1_base, {lg_disable.GP_KEY: lg_disable.GP_KEY_VALUE})))
    return payloads


def plan_rollback_payloads(which: str, original_bytes: Optional[bytes]) -> list:
    """Inject tuples for a rollback (same route, inverse payloads)."""
    if which == "g2":
        return [_inject_tuple(lg_disable.G2_DOMAIN, lg_disable.G2_REL_PATH,
                              plistlib.dumps({}))]
    if which == "g1":
        if not original_bytes:
            raise NuggetException(QCoreApplication.translate(
                "Nugget",
                "Liquid Glass Disable (Beta 1): no saved original "
                ".GlobalPreferences.plist for this device, so there is "
                "nothing safe to roll back to."))
        try:
            parsed = lg_disable.load_plist_dict(original_bytes)
        except Exception:
            parsed = None
        if not isinstance(parsed, dict):
            raise NuggetException(QCoreApplication.translate(
                "Nugget",
                "Liquid Glass Disable (Beta 1): the saved original "
                ".GlobalPreferences.plist is unreadable, so it was NOT "
                "written back."))
        return [_inject_tuple(lg_disable.G1_DOMAIN, lg_disable.G1_REL_PATH,
                              original_bytes)]
    raise NuggetException(QCoreApplication.translate(
        "Nugget", "Liquid Glass Disable (Beta 1): unknown rollback route."))


def payloads_from_staged_files(files, *, g1_active: bool, g2_active: bool):
    """Split the LGD records out of a staged apply pass.

    Returns ``(remaining_files, payloads)``. The payload bytes are built
    from the gate-approved effective plist for each active route, so any
    keys other enabled tweaks staged into the same files ride along with
    exactly the same content the sparse pass would have delivered.
    """
    wanted = {}
    if g2_active:
        wanted[(lg_disable.G2_DOMAIN, lg_disable.G2_REL_PATH)] = "G2"
    if g1_active:
        wanted[(lg_disable.G1_DOMAIN, lg_disable.G1_REL_PATH)] = "G1"
    if not wanted:
        return list(files), []

    payloads = []
    for (domain, rel_path), route in wanted.items():
        found, effective, problems = lg_disable._effective_plist(
            files, domain, rel_path)
        if problems:
            raise NuggetException(QCoreApplication.translate(
                "Nugget",
                "Liquid Glass Disable (Beta 1): the staged %1 payload "
                "could not be prepared for the full-backup route: %2").replace(
                    "%1", route).replace("%2", "; ".join(problems)))
        if not found or effective is None:
            raise NuggetException(QCoreApplication.translate(
                "Nugget",
                "Liquid Glass Disable (Beta 1): the staged %1 payload "
                "is missing, so the full-backup route was cancelled. "
                "Nothing was written.").replace("%1", route))
        payloads.append(_inject_tuple(
            domain, rel_path,
            plistlib.dumps(effective, fmt=plistlib.FMT_BINARY,
                           sort_keys=True)))

    remaining = []
    for f in files:
        key = ((getattr(f, "domain", "") or ""),
               (getattr(f, "restore_path", "") or "").lstrip("/"))
        if key not in wanted:
            remaining.append(f)
    return remaining, payloads


# --- injected-backup verification (pure, unit-tested) ----------------------

def device_dir_for(backup_root, udid) -> Path:
    """Resolve the device folder of a backup root (both layouts)."""
    candidate = Path(backup_root) / str(udid)
    if candidate.is_dir():
        return candidate
    return Path(backup_root)


def payload_disk_path(backup_root, udid, domain: str, rel_path: str) -> Path:
    file_id = hashlib.sha1(f"{domain}-{rel_path}".encode("utf-8")).hexdigest()
    return device_dir_for(backup_root, udid) / file_id[:2] / file_id


def verify_injected_payloads(backup_root, udid, payloads,
                             g1_base: Optional[dict] = None,
                             g1_allowed_new=(),
                             expect_candidate_key: bool = True) -> list:
    """Re-read the injected backup from disk and verify it end to end.

    Returns a list of problems ([] = the restore may proceed). This is a
    HARD gate: the caller must abort on any problem, before the device
    is touched — unlike the log-only payload check in the iOS 27 flow.
    """
    from src.restore.protective import verify_backup_payloads
    problems = []
    missing = verify_backup_payloads(backup_root, udid)
    if missing:
        problems.append(
            f"backup is incomplete: {len(missing)} manifest row(s) have "
            f"no payload on disk (e.g. {missing[:3]})")
    for domain, rel_path, data, *_rest in payloads:
        disk = payload_disk_path(backup_root, udid, domain, rel_path)
        if not disk.is_file():
            problems.append(f"{domain}/{rel_path}: injected payload "
                            "missing on disk")
            continue
        on_disk = disk.read_bytes()
        if on_disk != bytes(data):
            problems.append(f"{domain}/{rel_path}: injected payload "
                            "differs from the verified payload bytes")
            continue
        try:
            parsed = plistlib.loads(on_disk)
        except Exception as exc:
            problems.append(f"{domain}/{rel_path}: injected payload "
                            f"does not parse: {exc}")
            continue
        if not isinstance(parsed, dict):
            problems.append(f"{domain}/{rel_path}: injected payload root "
                            "is not a dict")
            continue
        if (domain, rel_path) == (lg_disable.G2_DOMAIN, lg_disable.G2_REL_PATH):
            if expect_candidate_key:
                value = parsed.get(lg_disable.GP_KEY)
                if type(value) is not bool or value is not lg_disable.GP_KEY_VALUE:
                    problems.append(
                        "G2: injected overlay does not carry "
                        f"{lg_disable.GP_KEY!r} as a real bool true")
        if (domain, rel_path) == (lg_disable.G1_DOMAIN, lg_disable.G1_REL_PATH):
            if not isinstance(g1_base, dict):
                problems.append(
                    "G1: no original device file was extracted from "
                    "this backup, so the whole-file payload cannot be "
                    "verified — refusing to restore it")
            else:
                allowed = {lg_disable.GP_KEY} | set(g1_allowed_new or ())
                problems.extend(lg_disable.diff_gate(
                    g1_base, parsed,
                    allowed_new=allowed,
                    allowed_override=allowed))
    return problems


# --- the route --------------------------------------------------------------

async def run_full_backup_route(udid: str, payloads: list, *,
                                update_label=lambda x: None,
                                backup_progress=lambda x: None,
                                restore_progress=lambda x: None,
                                reboot: bool = False,
                                g1_base: Optional[dict] = None,
                                g1_allowed_new=(),
                                expect_candidate_key: bool = True,
                                version: str = "", build: str = "") -> str:
    """Full backup → inject → hard-verify → restore. Returns backup root.

    Raises NuggetException with a user-facing message on every gated
    failure; device/protocol errors from the backup/restore itself
    propagate. Nothing writes to the device before the final restore,
    and every check above runs before that point.
    """
    from src.devicemanagement.session import lockdown_session
    from src.restore.inject import _is_encrypted_backup, inject_files_into_backup
    from src.restore.protective import (
        check_disk_space_for_backup, extract_gp_base_plist,
        new_protective_backup_dir, verify_backup_payloads,
    )
    from src.restore.restore import _restore_protective_backup, _start_mobilebackup2
    from src.utils.stall_watchdog import run_with_stall_watchdog

    if not payloads:
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "Liquid Glass Disable (Beta 1): the full-backup route was "
            "given nothing to deliver."))

    backup_root = new_protective_backup_dir(udid)

    # 1) Complete, unfiltered backup of the device (the iTunes/Finder
    #    kind), with disk space sized to the device checked first.
    update_label(QCoreApplication.translate(
        "Nugget",
        "Liquid Glass Disable: starting full backup of your device..."))
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
                    "Liquid Glass Disable (Beta 1): your device backup "
                    "is encrypted, and the full-backup route cannot "
                    "write into an encrypted backup safely. Turn off "
                    "backup encryption (Finder/iTunes: uncheck 'Encrypt "
                    "local backup'), then try again. Nothing was "
                    "written; your device was not changed."))
            await run_with_stall_watchdog(
                lambda tracking_cb: mb.backup(
                    full=True, backup_directory=backup_root,
                    progress_callback=tracking_cb),
                backup_progress,
                operation="backup",
            )
    device_dir = device_dir_for(backup_root, udid)
    if not (device_dir / "Manifest.db").is_file():
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "Liquid Glass Disable (Beta 1): the full backup did not "
            "produce a usable backup, so nothing was restored. Your "
            "device was not changed."))

    # 2) The backup itself must be complete — hard gate, not a log line.
    missing = verify_backup_payloads(backup_root, udid)
    if missing:
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "Liquid Glass Disable (Beta 1): the full backup is "
            "incomplete (%1 manifest file(s) have no data), so nothing "
            "was restored. Your device was not changed. The incomplete "
            "backup is kept on this computer for inspection.").replace("%1", str(len(missing))))

    # 3) The device's pristine global preferences, out of THIS backup:
    #    rollback source (first capture wins) and the G1 diff base.
    extracted_base = None
    with tempfile.TemporaryDirectory(prefix="workslop_lgd_full_") as tmp:
        dest = os.path.join(tmp, "device_gp.plist")
        extracted = extract_gp_base_plist(backup_root, udid, dest)
        if extracted and os.path.exists(extracted):
            with open(extracted, "rb") as fh:
                base_bytes = fh.read()
            try:
                extracted_base = lg_disable.load_plist_dict(base_bytes)
            except Exception:
                extracted_base = None
            if extracted_base is not None:
                try:
                    lg_disable.save_original_if_absent(udid, base_bytes, {
                        "udid": udid,
                        "ios_version": version,
                        "build": build,
                        "source": "full backup (26.6 route)",
                        "key_count": len(extracted_base),
                    })
                except OSError as save_err:
                    raise NuggetException(QCoreApplication.translate(
                        "Nugget",
                        "Liquid Glass Disable (Beta 1): the device's "
                        "original .GlobalPreferences.plist could not "
                        "be saved for rollback (%1). Nothing was "
                        "written.").replace("%1", str(save_err)))
    needs_g1 = any(
        (d, r) == (lg_disable.G1_DOMAIN, lg_disable.G1_REL_PATH)
        for d, r, *_ in payloads)
    if needs_g1 and diff_base is None:
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "Liquid Glass Disable (Beta 1): the device's own "
            ".GlobalPreferences.plist could not be read from the full "
            "backup, so the G1 payload cannot be verified. Nothing was "
            "restored; your device was not changed."))
    # A caller-supplied base wins: an apply verifies against the base its
    # payload was staged from, and a G1 rollback verifies the saved
    # original against itself. The base extracted from this backup is
    # the fallback and the rollback-save source.
    diff_base = g1_base if isinstance(g1_base, dict) else extracted_base

    # 4) Inject — encrypted backups are refused honestly, never faked.
    if _is_encrypted_backup(device_dir):
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "Liquid Glass Disable (Beta 1): your device backup is "
            "encrypted, and the full-backup route cannot write into an "
            "encrypted backup safely. Turn off backup encryption "
            "(Finder/iTunes: uncheck 'Encrypt local backup'), then try "
            "again. Nothing was restored; your device was not changed."))
    update_label(QCoreApplication.translate(
        "Nugget",
        "Liquid Glass Disable: writing the payload into the backup..."))
    injected, unchanged, failed = await asyncio.to_thread(
        inject_files_into_backup, backup_root, udid, payloads)
    if failed or injected + unchanged != len(payloads):
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "Liquid Glass Disable (Beta 1): the payload could not be "
            "written into the backup (%1 of %2 file(s) failed), so "
            "nothing was restored. Your device was not changed.").replace("%1", str(failed)).replace("%2", str(len(payloads))))

    # 5) Re-verify the injected backup from disk — hard gate.
    problems = verify_injected_payloads(
        backup_root, udid, payloads, g1_base=diff_base,
        g1_allowed_new=g1_allowed_new,
        expect_candidate_key=expect_candidate_key)
    if problems:
        raise NuggetException(QCoreApplication.translate(
            "Nugget",
            "Liquid Glass Disable (Beta 1): the verification gate "
            "failed, so nothing was restored and your device was not "
            "changed:\n") + "\n".join(f"• {p}" for p in problems))

    # 6) Restore the complete backup (retry/watchdog-wrapped native
    #    restore), then reboot only if the caller asked for it.
    update_label(QCoreApplication.translate(
        "Nugget",
        "Liquid Glass Disable: restoring the full backup..."))
    async with lockdown_session(udid) as lc:
        await _restore_protective_backup(
            lc, backup_root, udid, reboot=False,
            progress_callback=restore_progress, backup_password="")
        if reboot:
            from src.restore import reboot_device
            await reboot_device(True, lc)
    return backup_root
