from PySide6.QtCore import QCoreApplication, Signal, QThread, QSettings
from PySide6.QtWidgets import QMessageBox
from typing import Optional
# Module-level on purpose: the async workers below (``RestoreCacheThread.
# _restore``, ``ResetPairingThread``) awaited/used ``asyncio`` while only
# importing it inside another method's scope, which is a NameError.
import asyncio
import os
import queue
import traceback
import threading

# Qt-free shared type (kept here for backwards-compatible import paths forwards
# to the same class the backend uses).
from src.utils.alerts import ApplyAlertMessage
from src.exceptions.nugget_exception import NuggetException
from src.devicemanagement.session import install_windows_selector_policy


class _SudoState:
    """Thread-safe sudo password storage."""
    def __init__(self):
        self._lock = threading.Lock()
        self._pwd: Optional[str] = None

    def get_pwd(self) -> Optional[str]:
        with self._lock:
            pwd = self._pwd
            self._pwd = None
            return pwd

    def set_pwd(self, pwd: Optional[str]):
        with self._lock:
            self._pwd = pwd


_sudo_state = _SudoState()


def get_sudo_pwd() -> Optional[str]:
    return _sudo_state.get_pwd()


def set_sudo_pwd(pwd: Optional[str]):
    _sudo_state.set_pwd(pwd)


class ApplyThread(QThread):
    progress = Signal(str)
    alert = Signal(object)  # ApplyAlertMessage or None for sudo prompt
    finished_with_result = Signal(bool, str)  # success, error_message
    request_text = Signal(str, str, object)  # title, label, result box (main-thread prompt)
    choice_prompt = Signal(str, str, object)  # title, text, result box ("abort"/"resume", main-thread prompt)
    # WorkSlop: emitted (from the worker thread) with the backup root the
    # moment the live protective device backup reaches 100%.
    backup_finished = Signal(str)

    # Only the password prompt is guarded by a timeout. The apply/restore itself
    # is allowed to run to completion: a three-phase protective restore can
    # legitimately exceed 10 minutes waiting for the device to reboot, and
    # forcibly terminating the worker thread mid-restore (QThread.terminate)
    # would corrupt the device state.
    _PROMPT_TIMEOUT_SEC = 10 * 60

    def __init__(self, manager, settings: QSettings, reset_pages=None):
        super().__init__()
        self.manager = manager
        self.settings = settings
        self.reset_pages = reset_pages
        self.success = False
        self._error_msg: str = ""

    def prompt_password(self, title: str, label: str) -> Optional[str]:
        # Modal dialogs must be built on the main thread (macOS raises
        # NSInternalInconsistencyException otherwise), so relay the request
        # through a queued signal while this worker thread blocks on a queue.
        box = queue.Queue(maxsize=1)
        self.request_text.emit(title, label, box)
        try:
            return box.get(timeout=self._PROMPT_TIMEOUT_SEC)
        except queue.Empty:
            return None

    def prompt_user_choice(self, title: str, text: str) -> str:
        """Ask the user for a two-way decision on the main thread.

        Queued signal, same pattern as ``prompt_password``. Returns the
        decision the main-thread dialog boxed up: "abort" or "resume"
        ("abort" on timeout so a stale worker never hangs the restore
        forever).
        """
        box = queue.Queue(maxsize=1)
        self.choice_prompt.emit(title, text, box)
        try:
            return box.get(timeout=self._PROMPT_TIMEOUT_SEC)
        except queue.Empty:
            return "abort"

    def run(self):
        install_windows_selector_policy()  # Windows: pmd3 selector loop (session.py)
        import logging
        from src.controllers.nugget_logger import log_context
        self._log = logging.getLogger("WorkSlop.apply")
        mode = "reset" if self.reset_pages is not None else "apply"
        try:
            log_context(f"START {mode}",
                        name=self.manager.get_current_device_name() or "unknown",
                        model=self.manager.get_current_device_model() or "unknown",
                        ios=self.manager.get_current_device_version() or "unknown",
                        build=self.manager.get_current_device_build() or "unknown",
                        udid=self.manager.get_current_device_udid() or "unknown")
            self._do_work()
            self.success = True
            self._error_msg = ""
            _journal_path = getattr(self.manager, "last_apply_journal_path", None)
            if _journal_path:
                log_context("APPLY JOURNAL", path=_journal_path)
            log_context(f"FINISH {mode} OK")
            self.finished_with_result.emit(True, "")
        except Exception as e:
            self.success = False
            self._error_msg = f"{type(e).__name__}: {e}"
            traceback_str = traceback.format_exc()
            self._log.error("%s failed: %s\n%s", mode, e, traceback_str)
            self.alert.emit(ApplyAlertMessage(
                f"Operation failed: {e}",
                title="Error",
                icon=QMessageBox.Critical,
                detailed_txt=traceback_str,
                exc_type=type(e),
                exc_value=e,
            ))
            self.finished_with_result.emit(False, self._error_msg)

    def update_label(self, txt: str):
        if txt == 'sudo_pwd':
            self.alert.emit(None)
        else:
            self._log.info("progress: %s", txt)
            self.progress.emit(txt)

    def alert_window(self, msg: ApplyAlertMessage):
        if msg is not None:
            self._log.info("alert: %s | %s", getattr(msg, "title", ""), getattr(msg, "txt", ""))
        self.alert.emit(msg)

    def _do_work(self):
        if self.reset_pages is None:
            self.manager.apply_changes(self.update_label, self.alert_window,
                                       self.prompt_password, self.prompt_user_choice,
                                       on_backup_complete=self.backup_finished.emit)
        else:
            self.manager.reset_tweaks(self.reset_pages, self.settings, self.update_label,
                                      self.alert_window, self.prompt_user_choice)


class RestoreCacheThread(QThread):
    """Restore the last protective backup cache (post-failure data recovery).

    Mirrors ``apply_changes``' Phase 1+3 so a protective backup that was kept
    on disk after a wedged/failed apply can be restored standalone — e.g. when
    the iPhone was not unlocked in time and Phase 3 was aborted. Runs in a
    background thread to keep the UI responsive (the restore waits for the
    device and for the user to unlock).
    """
    progress = Signal(str)
    alert = Signal(object)
    finished_with_result = Signal(bool, str)
    choice_prompt = Signal(str, str, object)  # title, text, result box ("abort"/"resume", main-thread prompt)

    # Same guard as ApplyThread: a stale worker must never block the recovery
    # forever. The media push itself is NOT force-terminated — this only bounds
    # how long the dialog waits for the user.
    _PROMPT_TIMEOUT_SEC = 10 * 60

    def __init__(self, manager):
        super().__init__()
        self.manager = manager

    def prompt_user_choice(self, title: str, text: str) -> str:
        """Ask the user for a two-way decision on the main thread.

        Same queued-signal pattern as ``ApplyThread.prompt_user_choice``:
        modal dialogs must be built on the main thread, so the request is
        relayed and this worker blocks on the boxed result. Returns "abort" or
        "resume" ("abort" on timeout).
        """
        box = queue.Queue(maxsize=1)
        self.choice_prompt.emit(title, text, box)
        try:
            return box.get(timeout=self._PROMPT_TIMEOUT_SEC)
        except queue.Empty:
            return "abort"

    def update_label(self, txt: str):
        self.progress.emit(txt)

    def run(self):
        install_windows_selector_policy()  # Windows: pmd3 selector loop (session.py)
        import logging
        from src.controllers.nugget_logger import log_context
        log = logging.getLogger("WorkSlop.restore_cache")
        try:
            log_context("START restore-cache",
                        udid=self.manager.get_current_device_udid() or "unknown")
            self._do_work()
            log_context("FINISH restore-cache OK")
            self.finished_with_result.emit(True, "")
        except Exception as e:
            traceback_str = traceback.format_exc()
            log.error("restore-cache failed: %s\n%s", e, traceback_str)
            self.alert.emit(ApplyAlertMessage(
                f"Failed to restore data from backup: {e}",
                title="Restore data",
                icon=QMessageBox.Critical,
                detailed_txt=traceback_str,
                exc_type=type(e),
                exc_value=e,
            ))
            self.finished_with_result.emit(False, f"{type(e).__name__}: {e}")

    def _do_work(self):
        import asyncio
        asyncio.run(self._restore())

    async def _restore(self):
        import tempfile
        from pathlib import Path
        from src.restore.protective import (
            make_protective_working_copy,
            clean_backup_for_restore,
            verify_backup_payloads,
            find_latest_protective_backup,
        )
        from src.restore.restore import _restore_protective_backup
        from src.restore.afc_media import (
            afc_media_dir_for, describe_media_store, media_store_verified,
            restore_media_via_afc,
        )
        from src.devicemanagement.session import lockdown_session

        udid = self.manager.get_current_device_udid()
        if not udid:
            raise RuntimeError("No device selected.")
        self.update_label("Locating protective backup...")
        # Prefer the cache master. Fall back to a live protective backup left
        # behind by an interrupted apply — after Phase 2 wiped the device that
        # directory is the only copy of the user's data, so the recovery path
        # has to be able to reach it.
        base = self._find_cache_base(udid)
        source_root = str(base / "master") if base is not None else None
        if source_root is None:
            source_root = find_latest_protective_backup(udid)
        if source_root is None:
            raise RuntimeError(
                "No protective backup found for this device. Live backups are "
                "kept in the app data folder; cache masters live in a temp "
                "folder and are lost on reboot.")
        # Pre-flight: refuse a half-written source manifest up front instead of
        # failing mid-device-restore with an opaque MBErrorDomain/205. The
        # restore only ever prunes/injects on a temp working copy, so a corrupt
        # Manifest.db here means an earlier apply/restore left the source
        # damaged; an encrypted manifest is skipped (it is not valid sqlite
        # until decrypted with the password below).
        if not self._backup_password():
            from src.restore.protective import _validate_sqlite_db
            src_manifest = Path(source_root) / udid / "Manifest.db"
            if not src_manifest.is_file():
                src_manifest = Path(source_root) / "Manifest.db"
            if not _validate_sqlite_db(src_manifest):
                raise RuntimeError(
                    "The protective backup's Manifest.db is corrupted or "
                    "incomplete (left half-written by an interrupted restore). "
                    "Apply tweaks again to rebuild a fresh backup, or remove "
                    "the cached backup from Settings → Backup Cache.")
        self.update_label("Building working copy of the backup...")
        working_root = await asyncio.to_thread(
            make_protective_working_copy, source_root, udid)
        # A live backup taken with the AFC channel kept bulk photo trees beside
        # the run dir (never uploaded to mobilebackup2), so its manifest rows
        # for those trees must be pruned the same way or the restore fails with
        # payload-missing rows. A cache master now carries photos the same way:
        # its Persistent per-device media store lives at
        # ``<base>/media/<udid>``. Either way, only a media dir whose last pull
        # finished cleanly is treated as the AFC source — "the folder has files
        # in it" is not enough, because a partial pull would then let the prune
        # below delete the backup's own copy of the photos.
        media_dir = afc_media_dir_for(source_root)
        from src.restore.protective_cache import peek_cache_info
        cache_info = peek_cache_info(udid)
        if cache_info is not None and cache_info.get("media_afc"):
            from pathlib import Path as _Path
            try:
                base = _Path(source_root).parent.parent  # <base>/master/<udid> -> <base>
            except Exception:
                base = None
            if base is not None:
                media_dir = str(base / "media" / udid)
        media_has_content = media_store_verified(media_dir)
        removed_rows, removed_files = await asyncio.to_thread(
            clean_backup_for_restore, working_root, udid,
            include_keychain=bool(self._backup_password()),
            manifest_password=self._backup_password(),
            exclude_afc_media_trees=media_has_content)
        self.update_label(
            f"Prepared backup (-{removed_rows} pruned rows). Connecting to device...")
        missing = await asyncio.to_thread(
            verify_backup_payloads, working_root, udid,
            self._backup_password())
        if missing:
            raise RuntimeError(
                f"{len(missing)} manifest rows lack payloads; the backup is "
                f"incomplete and cannot be restored. Remove the cache and apply "
                f"again to rebuild it.")

        lc = None
        async with lockdown_session(udid) as _ld:
            lc = _ld
            # the retry loop inside _restore_protective_backup reconnects as
            # needed after the wipe-induced lock and drops
            await _restore_protective_backup(
                lc, working_root, udid, reboot=False,
                progress_callback=self._progress_cb,
                backup_password=self._backup_password(),
                skip_apps=True)
            # Photos/videos taken through the AFC channel live beside the
            # source dir: a live backup keeps them next to the device_backup
            # dir, a cache master at ``<base>/media/<udid>``. Either way the
            # media dir rides the same AFC-located store and has to be pushed
            # back over AFC after the restore.
            if media_dir:
                if not os.path.isdir(media_dir) or not os.listdir(media_dir):
                    raise NuggetException(
                        f"AFC media store is missing or empty ({media_dir}) — "
                        f"the photos were not backed up before the wipe. "
                        f"Aborting instead of pretending the restore finished.")
                # the store is the ONLY copy of the photos once the wipe is
                # done, so an incomplete push must abort the apply instead of
                # letting it report success with missing media
                self.update_label(
                    f"Restoring photos/videos over AFC ({describe_media_store(media_dir)})...")
                pushed = await restore_media_via_afc(
                    lc, media_dir, progress_callback=self._progress_cb,
                    prompt_choice=self.prompt_user_choice,
                    unlock_prompt=(
                        QCoreApplication.tr("Device stayed locked"),
                        QCoreApplication.tr(
                            "The device has not been unlocked long enough to "
                            "push your photos and videos back.\n\n"
                            "Unlock it, enter your passcode, and keep it "
                            "connected via USB, then choose:\n\n"
                            "  \u2022 Resume \u2014 keep waiting for the device "
                            "to be unlocked and push your photos.\n"
                            "  \u2022 Abort \u2014 stop now. Your photos are "
                            "still safe in the backup cache on this computer, "
                            "but they will not be on the device yet.")
                    ))
                if pushed.get("failed"):
                    raise NuggetException(
                        f"AFC media restore failed for {len(pushed['failed'])} "
                        f"file(s) (e.g. {pushed['failed'][:3]}) — the photos on "
                        f"the device are incomplete")
        self.update_label("Data restored successfully.")

    def _progress_cb(self, value):
        if isinstance(value, str):
            self.update_label(value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            self.update_label(f"Restoring... {value:.1f}%")

    def _backup_password(self) -> str:
        try:
            return self.manager._get_backup_password()
        except Exception:
            return ""

    def _find_cache_base(self, udid: str):
        import tempfile
        from pathlib import Path
        from src.restore.storage import cache_base, is_custom_backup_dir
        bases = []
        try:
            bases.append(Path(tempfile.gettempdir()) / "goldennugget_protective_cache")
        except Exception:
            pass
        bases.append(cache_base())
        if is_custom_backup_dir():
            # A cache created under the previous default location may still
            # exist there; read it so it can be migrated on the next refresh.
            from PySide6.QtCore import QStandardPaths
            try:
                bases.append(Path(QStandardPaths.writableLocation(
                    QStandardPaths.AppDataLocation)) / "GoldenNugget" / "backup_cache")
            except Exception:
                pass
        for base in bases:
            if (base / "master" / udid / "Manifest.db").is_file():
                return base
            if (base / f"{udid}.json").is_file():
                return base
        return None


class RestoreFullBackupThread(QThread):
    """Restore a standard full backup folder (format 1 of the Restore menu).

    The user picks a backup directory — the standard mobilebackup2 layout
    (Manifest.db/Manifest.plist + Info.plist), e.g. one saved via the
    backup-reveal feature — and it is pushed back to the device with
    mobilebackup2, then the device reboots. Format 2 (GoldenNugget's own
    protective backup) is handled by ``RestoreCacheThread``.
    """
    progress = Signal(str)
    alert = Signal(object)
    finished_with_result = Signal(bool, str)
    request_text = Signal(str, str, object)  # title, label, result box (main-thread password prompt)
    choice_prompt = Signal(str, str, object)  # title, text, result box ("abort"/"resume", main-thread prompt)

    _PROMPT_TIMEOUT_SEC = 10 * 60

    def __init__(self, manager, backup_dir, backup_password=None):
        super().__init__()
        self.manager = manager
        self.backup_dir = backup_dir
        self._preset_password = backup_password or ""

    def prompt_password(self, title: str, label: str) -> Optional[str]:
        # Same queued-signal pattern as ApplyThread: modal dialogs must be
        # built on the main thread, so the request is relayed while this
        # worker thread blocks on the queue.
        box = queue.Queue(maxsize=1)
        self.request_text.emit(title, label, box)
        try:
            return box.get(timeout=self._PROMPT_TIMEOUT_SEC)
        except queue.Empty:
            return None

    def update_label(self, txt: str):
        self.progress.emit(txt)

    def _progress_cb(self, value):
        if isinstance(value, str):
            self.update_label(value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            self.update_label(QCoreApplication.translate(
                "Nugget", "Restoring backup... ({0:.1f}%)").format(value))

    def run(self):
        install_windows_selector_policy()  # Windows: pmd3 selector loop (session.py)
        import logging
        from src.controllers.nugget_logger import log_context
        log = logging.getLogger("WorkSlop.restore_full")
        try:
            log_context("START restore-full",
                        udid=self.manager.get_current_device_udid() or "unknown",
                        backup_dir=self.backup_dir)
            asyncio.run(self._restore())
            log_context("FINISH restore-full OK")
            self.finished_with_result.emit(True, "")
        except Exception as e:
            traceback_str = traceback.format_exc()
            log.error("restore-full failed: %s\n%s", e, traceback_str)
            self.alert.emit(ApplyAlertMessage(
                f"Failed to restore full backup: {e}",
                title="Restore full backup",
                icon=QMessageBox.Critical,
                detailed_txt=traceback_str,
                exc_type=type(e),
                exc_value=e,
            ))
            self.finished_with_result.emit(False, f"{type(e).__name__}: {e}")

    async def _restore(self):
        import plistlib
        from pathlib import Path
        from src.devicemanagement.session import lockdown_session
        from src.restore.restore import _start_mobilebackup2
        from src.restore import reboot_device

        udid = self.manager.get_current_device_udid()
        if not udid:
            raise RuntimeError("No device selected.")
        root = Path(self.backup_dir)
        has_manifest = (root / "Manifest.db").is_file() or (root / "Manifest.plist").is_file()
        if not has_manifest or not (root / "Info.plist").is_file():
            raise RuntimeError(
                "This folder is not a standard iPhone backup "
                "(expected Manifest.db/Manifest.plist and Info.plist inside).")

        # Encrypted backup -> the backup password is required to restore.
        password = self._preset_password
        try:
            with open(root / "Manifest.plist", "rb") as f:
                is_encrypted = bool(plistlib.load(f).get("IsEncrypted"))
        except Exception:
            is_encrypted = False
        if is_encrypted and not password:
            password = self.prompt_password(
                QCoreApplication.translate("Nugget", "Backup Password"),
                QCoreApplication.translate(
                    "Nugget",
                    "This backup is encrypted. Enter its backup password:")) or ""
        if is_encrypted and not password:
            raise RuntimeError("This backup is encrypted — its password is required.")

        self.update_label(QCoreApplication.translate(
            "Nugget", "Connecting to device..."))
        async with lockdown_session(udid) as lc:
            async with _start_mobilebackup2(lc) as mb:
                await mb.restore(
                    str(root), system=True, reboot=False, copy=False,
                    source=".", skip_apps=False,
                    progress_callback=self._progress_cb,
                    password=password or None)
            self.update_label(QCoreApplication.translate(
                "Nugget", "Rebooting device..."))
            await reboot_device(True, lc)


class GestaltApplyThread(QThread):
    """Apply only the MobileGestalt tweaks (Nugget's gestalt flow).

    Runs ``device_manager.apply_gestalt_tweaks`` off the UI thread. Version
    rule follows leminlimez/Nugget 100%: never on iOS 26.2+.
    """
    progress = Signal(str)
    alert = Signal(object)
    finished_with_result = Signal(bool, str)

    def __init__(self, manager):
        super().__init__()
        self.manager = manager

    def update_label(self, txt: str):
        self.progress.emit(txt)

    def run(self):
        install_windows_selector_policy()  # Windows: pmd3 selector loop (session.py)
        import logging
        from src.controllers.nugget_logger import log_context
        log = logging.getLogger("WorkSlop.gestalt")
        try:
            log_context("START gestalt-apply",
                        udid=self.manager.get_current_device_udid() or "unknown")
            alert = asyncio.run(self.manager._apply_gestalt_tweaks(
                update_label=self.update_label))
            log_context("FINISH gestalt-apply OK")
            if alert is not None:
                self.alert.emit(alert)
            self.finished_with_result.emit(True, "")
        except Exception as e:
            traceback_str = traceback.format_exc()
            log.error("gestalt-apply failed: %s\n%s", e, traceback_str)
            self.alert.emit(ApplyAlertMessage(
                f"Failed to apply MobileGestalt tweaks: {e}",
                title="MobileGestalt",
                icon=QMessageBox.Critical,
                detailed_txt=traceback_str,
                exc_type=type(e),
                exc_value=e,
            ))
            self.finished_with_result.emit(False, f"{type(e).__name__}: {e}")


class FullBackupThread(QThread):
    """Create a real FULL iPhone backup — the iTunes way.

    Uses mobilebackup2 ``backup(full=True)`` with no filter callback, so
    *everything* is copied: this is exactly what iTunes/Finder does, not the
    selective protective backup the tweak flow uses. The result is a standard
    backup folder (``<save dir>/<udid>/`` with Manifest.db + Info.plist) that
    can be copied into iTunes' MobileSync/Backup folder.
    """
    progress = Signal(str)
    alert = Signal(object)
    finished_with_result = Signal(bool, str)
    choice_prompt = Signal(str, str, object)  # title, text, result box ("abort"/"resume", main-thread prompt)
    # Emitted with the finished backup directory on success.
    backup_finished = Signal(str)

    _PROMPT_TIMEOUT_SEC = 10 * 60

    def __init__(self, manager, save_dir):
        super().__init__()
        self.manager = manager
        self.save_dir = save_dir

    def prompt_user_choice(self, title: str, text: str) -> str:
        box = queue.Queue(maxsize=1)
        self.choice_prompt.emit(title, text, box)
        try:
            return box.get(timeout=self._PROMPT_TIMEOUT_SEC)
        except queue.Empty:
            return "abort"

    def update_label(self, txt: str):
        self.progress.emit(txt)

    def _progress_cb(self, value):
        # mobilebackup2 reports 0-100 floats; guard like the apply path does.
        if isinstance(value, str):
            self.update_label(value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            self.update_label(QCoreApplication.translate(
                "Nugget", "Backing up... ({0:.1f}%)").format(value))

    def run(self):
        install_windows_selector_policy()  # Windows: pmd3 selector loop (session.py)
        import logging
        from src.controllers.nugget_logger import log_context
        log = logging.getLogger("WorkSlop.full_backup")
        try:
            log_context("START full-backup",
                        udid=self.manager.get_current_device_udid() or "unknown",
                        save_dir=self.save_dir)
            backup_path = asyncio.run(self._backup())
            log_context("FINISH full-backup OK")
            self.backup_finished.emit(backup_path)
            self.finished_with_result.emit(True, "")
        except Exception as e:
            traceback_str = traceback.format_exc()
            log.error("full-backup failed: %s\n%s", e, traceback_str)
            self.alert.emit(ApplyAlertMessage(
                f"Failed to create full backup: {e}",
                title="Full backup",
                icon=QMessageBox.Critical,
                detailed_txt=traceback_str,
                exc_type=type(e),
                exc_value=e,
            ))
            self.finished_with_result.emit(False, f"{type(e).__name__}: {e}")

    async def _backup(self) -> str:
        import os
        from src.devicemanagement.session import lockdown_session
        from src.restore.restore import _start_mobilebackup2

        udid = self.manager.get_current_device_udid()
        if not udid:
            raise RuntimeError("No device selected.")
        save_dir = os.path.abspath(self.save_dir)
        os.makedirs(save_dir, exist_ok=True)

        self.update_label(QCoreApplication.translate(
            "Nugget", "Connecting to device..."))
        async with lockdown_session(udid) as lc:
            self.update_label(QCoreApplication.translate(
                "Nugget", "Starting full backup..."))
            async with _start_mobilebackup2(lc) as mb:
                # full=True + NO filter_callback = complete backup, the way
                # iTunes/Finder does it. mobilebackup2 creates the
                # <udid> subfolder inside backup_directory itself.
                await mb.backup(full=True, backup_directory=save_dir,
                                progress_callback=self._progress_cb)
        backup_path = os.path.join(save_dir, udid)
        if not os.path.isdir(backup_path):
            # Fallback: some layouts write directly into the given dir.
            backup_path = save_dir
        return backup_path


class ProtectiveBackupThread(QThread):
    """Run the selective protective backup on demand (the "Backup Biasa").

    This is the SAME backup the iOS 27 apply flow runs automatically before
    touching the device: photos, messages, contacts, Apple ID / settings
    data, and the keychain when the device backup is encrypted. It is NOT a
    full backup — it only covers what the tweak flow needs to restore.
    """
    progress = Signal(str)
    alert = Signal(object)
    finished_with_result = Signal(bool, str)
    # Emitted with the finished backup directory on success.
    backup_finished = Signal(str)

    def __init__(self, manager):
        super().__init__()
        self.manager = manager

    def update_label(self, txt: str):
        self.progress.emit(txt)

    def _progress_cb(self, value):
        # perform_protective_backup reports either text or 0-100 floats.
        if isinstance(value, str):
            self.update_label(value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            self.update_label(QCoreApplication.translate(
                "Nugget", "Backing up... ({0:.1f}%)").format(value))

    def run(self):
        install_windows_selector_policy()  # Windows: pmd3 selector loop (session.py)
        import logging
        from src.controllers.nugget_logger import log_context
        log = logging.getLogger("WorkSlop.protective_backup")
        try:
            udid = self.manager.get_current_device_udid()
            log_context("START manual-protective-backup",
                        udid=udid or "unknown")
            backup_root = asyncio.run(self._backup(udid))
            log_context("FINISH manual-protective-backup OK")
            self.backup_finished.emit(backup_root)
            self.finished_with_result.emit(True, "")
        except Exception as e:
            traceback_str = traceback.format_exc()
            log.error("manual-protective-backup failed: %s\n%s", e, traceback_str)
            self.alert.emit(ApplyAlertMessage(
                f"Failed to create protective backup: {e}",
                title="Protective backup",
                icon=QMessageBox.Critical,
                detailed_txt=traceback_str,
                exc_type=type(e),
                exc_value=e,
            ))
            self.finished_with_result.emit(False, f"{type(e).__name__}: {e}")

    async def _backup(self, udid) -> str:
        import os
        from src.devicemanagement.session import lockdown_session
        from src.restore.protective import (
            new_protective_backup_dir, perform_protective_backup,
        )
        from src.restore.afc_media import afc_media_enabled

        if not udid:
            raise RuntimeError("No device selected.")
        backup_root = new_protective_backup_dir(udid)

        self.update_label(QCoreApplication.translate(
            "Nugget", "Connecting to device..."))
        async with lockdown_session(udid) as lc:
            self.update_label(QCoreApplication.translate(
                "Nugget", "Backing up device..."))
            await perform_protective_backup(
                lc, backup_root,
                progress_callback=self._progress_cb,
                include_photos=True, include_posterboard=False,
                include_keychain=None,
                include_afc_media=afc_media_enabled(
                    self.manager.pref_manager.use_afc_media),
            )
        return backup_root


class CacheUpdateThread(QThread):
    """Force a refresh of the backup cache master (pre-apply "Update Cache").

    Runs ``device_manager.refresh_backup_cache`` in a background thread so
    the pre-apply summary can freshen the cache (and its creation date) before
    the user confirms the apply. Unlike ``ApplyThread`` it never applies tweaks
    and never teleports to a restore.
    """
    progress = Signal(str)
    alert = Signal(object)  # ApplyAlertMessage
    finished_with_result = Signal(bool, str)  # success, error_message

    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.success = False
        self._error_msg = ""

    def update_label(self, txt: str):
        self.progress.emit(txt)

    def run(self):
        install_windows_selector_policy()  # Windows: pmd3 selector loop (session.py)
        import logging
        import asyncio
        from src.controllers.nugget_logger import log_context
        log = logging.getLogger("WorkSlop.cache_update")
        try:
            log_context("START cache-update",
                        udid=self.manager.get_current_device_udid() or "unknown")
        except Exception:
            pass
        try:
            asyncio.run(self.manager.refresh_backup_cache(self.update_label))
            self.success = True
            self._error_msg = ""
            log.info("cache update finished OK")
        except Exception as e:
            self.success = False
            self._error_msg = f"{type(e).__name__}: {e}"
            traceback_str = traceback.format_exc()
            log.error("cache update failed: %s\n%s", e, traceback_str)
            self.alert.emit(ApplyAlertMessage(
                f"Failed to update the backup cache: {e}",
                title="Update Cache",
                icon=QMessageBox.Critical,
                detailed_txt=traceback_str,
                exc_type=type(e),
                exc_value=e,
            ))
        self.finished_with_result.emit(self.success, self._error_msg)


class RefreshDevicesThread(QThread):
    alert = Signal(object)
    # Fires (queued) each time a device is appended during enumeration so
    # the UI can show it immediately instead of waiting for the whole list.
    device_found = Signal()

    def __init__(self, manager, settings):
        super().__init__()
        self.manager = manager
        self.settings = settings

    def alert_window(self, msg: ApplyAlertMessage):
        self.alert.emit(msg)

    def run(self):
        install_windows_selector_policy()  # Windows: pmd3 selector loop (session.py)
        import logging
        log = logging.getLogger("WorkSlop.refresh")
        try:
            self.manager.get_devices(
                self.settings, self.alert_window,
                on_device_found=lambda _dev: self.device_found.emit())
        except Exception as e:
            traceback_str = traceback.format_exc()
            log.error("refresh devices failed: %s\n%s", e, traceback_str)
            self.alert.emit(ApplyAlertMessage(
                f"Failed to refresh devices: {e}",
                title="Error",
                icon=QMessageBox.Critical,
                detailed_txt=traceback_str,
                exc_type=type(e),
                exc_value=e,
            ))


class ResetPairingThread(QThread):
    """Ran-no-device-io pair reset (unpair + pair) on a worker thread so the
    settings page keeps painting while lockdown talks to the device."""

    done = Signal(bool, str)  # success, error message

    def __init__(self, manager):
        super().__init__()
        self.manager = manager

    def run(self):
        install_windows_selector_policy()  # Windows: pmd3 selector loop (session.py)
        import logging
        import asyncio
        log = logging.getLogger("WorkSlop.pairing")
        try:
            asyncio.run(self.manager._reset_device_pairing())
        except Exception as e:
            traceback_str = traceback.format_exc()
            log.error("reset pairing failed: %s\n%s", e, traceback_str)
            self.done.emit(False, str(e))
            return
        self.done.emit(True, "")