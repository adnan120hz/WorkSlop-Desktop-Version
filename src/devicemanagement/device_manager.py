import asyncio
import os.path
import plistlib
import shutil
import sys
import traceback

from tempfile import TemporaryDirectory
from typing import Optional

from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import QSettings, QCoreApplication

from packaging.version import Version

from pymobiledevice3 import usbmux
from pymobiledevice3.services.mobile_config import MobileConfigService
from pymobiledevice3.exceptions import MuxException, PasswordRequiredError, ConnectionTerminatedError, AccessDeniedError, InvalidServiceError
from pymobiledevice3.services.mobilebackup2 import Mobilebackup2Service
import pymobiledevice3.service_connection as _sc


from src.devicemanagement.session import lockdown_session
from src.exceptions.device_errors import is_device_locked_error as _is_device_locked_error
from src.controllers.hotload import HotLoad
from src.restore.skip_setup27 import build_cloud_config

# Bump SSL handshake timeout from 10s to 60s for all lockdown services.
_sc.DEFAULT_SSL_HANDSHAKE_TIMEOUT = 60

# Temporarily allow writing up to this many PosterBoard tendies in a single
# restore. Applying more than one tendie at once can race PosterBoard's sqlite
# regeneration, so the count is capped.
MAX_TENDIES_PER_RESTORE = 5

from src.devicemanagement.constants import (
    Device, Version, is_device_supported, mobilegestalt_decision,
)
from src.tweaks.capabilities import (
    canonical_tweak_id,
    clear_audit_research_only_state, clear_unsupported_mobilegestalt_state,
    is_audit_research_only, is_audit_target, is_removed_tweak,
    requires_gestalt, tweak_deliverability, validate_custom_resolution,
)
from src.devicemanagement.data_singleton import DataSingleton
from .preference_manager import PreferenceManager

# Wave 10 Apply Journal (separate from restore/lastapply.py, which stays
# the sparse-signature optimization record and is never an audit record).
from src.controllers.apply_journal import (
    begin_journal, value_summary,
    TW_DELIVERED, TW_FAILED, TW_NOT_DELIVERED, TW_SKIPPED, TW_STAGED,
)
from src.tweaks.registry import SPECS_BY_ID, Kind as _SpecKind

from src.utils.alerts import ApplyAlertMessage
from src.utils.pages import Page
from src.controllers.path_handler import fix_windows_path

from src.exceptions.nugget_exception import NuggetException

from src.tweaks.tweaks import (
    tweaks, TweakID, BasicPlistTweak, AdvancedPlistTweak, NullifyFileTweak,
    StatusBarTweak, MobileGestaltTweak, MobileGestaltPickerTweak,
    MobileGestaltMultiTweak, MobileGestaltCacheDataTweak, FeatureFlagTweak,
    EligibilityTweak, AITweak, BookRestoreFileTweak,
)
from src.tweaks.custom_gestalt_tweaks import CustomGestaltTweaks
from src.tweaks.status_bar.statusbar_archive import build_reset_archive
from src.tweaks.posterboard.posterboard_tweak import PosterboardTweak
from src.tweaks.posterboard.template_options.templates_tweak import TemplatesTweak
from src.tweaks.icon_themes.icon_themes_tweak import IconThemesTweak
from src.tweaks.basic_plist_locations import FileLocation

from src.restore.restore import restore_files, FileToRestore
from src.restore.afc_media import (
    afc_media_dir_for, afc_media_enabled, describe_media_store,
    media_store_verified,
)
from src.restore.protective import log_error, log_info, log_warn

def get_files_list_str(files_list: list[FileToRestore] = None) -> str:
    files_str: str = ""
    if files_list != None:
        files_str = "FILES LIST:"
        print("\nFile List:\n")
        for file in files_list:
            file_info = f"\n    Domain: {file.domain}\n    Path: {file.restore_path}"
            files_str += file_info
            print(file_info)
    return files_str

def show_apply_error(e: Exception, update_label=lambda x: None, files_list: list[FileToRestore] = None):
    print(traceback.format_exc())
    update_label("Failed to restore")
    if "Find My" in str(e):
        return ApplyAlertMessage(QCoreApplication.tr("Find My must be disabled in order to use this tool."),
                       detailed_txt=QCoreApplication.tr("Disable Find My from Settings (Settings -> [Your Name] -> Find My) and then try again."))
    elif "Encrypted Backup MDM" in str(e):
        return ApplyAlertMessage(QCoreApplication.tr("Nugget cannot be used on this device. Click Show Details for more info."),
                       detailed_txt=QCoreApplication.tr("Your device is managed and MDM backup encryption is on. This must be turned off in order for Nugget to work. Please do not use Nugget on your school/work device!"))
    elif "SessionInactive" in str(e) or "ConnectionAbortedError" in str(e):
        return ApplyAlertMessage(QCoreApplication.tr("The session was terminated. Refresh the device list and try again."))
    elif "PasswordRequiredError" in str(e):
        return ApplyAlertMessage(QCoreApplication.tr("Device is password protected! You must trust the computer on your device."),
                       detailed_txt=QCoreApplication.tr("Unlock your device. On the popup, click \"Trust\", enter your password, then try again."))
    elif isinstance(e, ConnectionTerminatedError):
        files_str: str = get_files_list_str(files_list)
        return ApplyAlertMessage(QCoreApplication.tr("Device failed in sending files. The file list is possibly corrupted or has duplicates. Click Show Details for more info."),
                                 detailed_txt=files_str + "TRACEBACK:\n\n" + str(traceback.format_exc()))
    elif isinstance(e, AccessDeniedError):
        return ApplyAlertMessage(QCoreApplication.tr("Access denied while sending files."), detailed_txt="Try running the program with sudo.")
    elif isinstance(e, InvalidServiceError):
        return ApplyAlertMessage(QCoreApplication.tr("You must enable developer mode on your device. You can do it in the Settings app."),
                                 detailed_txt=QCoreApplication.tr("Applying tweaks requires developer mode.\n\nYou can enable this at the bottom of Settings > Privacy & Security > Developer Mode on your iPhone or iPad."))
    elif isinstance(e, NuggetException):
        return ApplyAlertMessage(str(e), detailed_txt=e.detailed_text)
    else:
        files_str: str = get_files_list_str(files_list)
        error_msg = type(e).__name__ + ": " + repr(e)
        # Check if this is a protective backup failure with a backup path
        backup_path = None
        error_str = str(e)
        if "protective backup kept at:" in error_str:
            import re
            match = re.search(r'protective backup kept at:\s*(\S+)', error_str)
            if match:
                backup_path = match.group(1)
        return ApplyAlertMessage(
            error_msg, 
            detailed_txt=files_str + "TRACEBACK:\n\n" + str(traceback.format_exc()),
            backup_path=backup_path
        )

class DeviceManager:
    ## Class Functions
    def __init__(self):
        self.devices: list[Device] = []
        self.data_singleton = DataSingleton()
        self.current_device_index = 0

        # preferences
        self.pref_manager = PreferenceManager(None)
        
        # Backup password (for encrypted backups)
        self._backup_password: Optional[str] = None

        # Encryption state as last seen by Phase 0's backup (None = not yet
        # known). Lets _apply_tweak_pass skip its own lockdown round-trip on
        # most applies — Phase 0 already paid for the check.
        self._known_backup_encryption: Optional[bool] = None

        # Set when the user chose to continue without data protection (e.g.
        # out of disk space) — Phase 1 must not re-run the protective backup.
        self._protective_backup_skipped = False

        # WorkSlop: root of the last finished live protective backup
        # (set when the 0->100% device backup completes in _live_backup).
        # The GUI reveals this path in the file manager so the user can
        # copy it somewhere safe.
        self.last_protective_backup_root: str | None = None
        
        # Wave 10 Apply Journal state for the running operation.
        self.last_apply_journal_path: str | None = None
        self._current_journal = None
        self._journal_error: str | None = None
        self._hotload_forced_daemon_keys: set = set()

        # Test mode
        self._test_mode = "--test-mode" in sys.argv

        # Human-readable detection diagnostics from the last enumeration
        # (empty on success). Home shows these when no device is found so
        # "No Device" always comes with the reason (cable/Trust/driver).
        self.detection_notes: list = []
    
    def _get_backup_password(self) -> str:
        """Get backup password from settings or return empty string."""
        if self._backup_password:
            return self._backup_password
        # Try to get from settings
        if self.pref_manager.settings:
            pwd = self.pref_manager.settings.value("backup_password", "", type=str)
            if pwd:
                self._backup_password = pwd
                return pwd
        return ""
    
    def get_devices(self, settings: QSettings, show_alert=lambda x: None,
                    on_device_found=None):
        # Guard against an unresponsive usbmuxd/lockdown hang blocking startup
        # forever. Enumeration of a handful of devices is normally near-instant,
        # so 60s is a generous ceiling. ``on_device_found`` (optional) fires
        # after each device is appended so the UI can show it immediately
        # instead of waiting for the whole list (user latency fix 2026-10-03).
        try:
            asyncio.run(asyncio.wait_for(
                self._get_devices(settings, show_alert, on_device_found),
                timeout=60))
        except asyncio.TimeoutError:
            show_alert(ApplyAlertMessage(
                txt=QCoreApplication.tr("Getting the device list timed out."),
                detailed_txt=QCoreApplication.tr(
                    "Device enumeration took too long. Check your USB connection and try again.")
            ))
    async def _get_devices(self, settings: QSettings, show_alert=lambda x: None,
                           on_device_found=None):
        # Test mode: use mock device already set up in main_app.py
        if self._test_mode:
            self.pref_manager.settings = settings
            return

        self.devices.clear()
        self.detection_notes = []
        # Detection diagnostics (user report 2026-10-03: "No Device" with
        # zero explanation, and slow detection). Every stage is logged with
        # timings so the log says WHERE seconds went instead of silence.
        import logging as _logging
        import time as _time
        _det = _logging.getLogger("WorkSlop.detection")
        _t0 = _time.monotonic()
        # handle errors when failing to get connected devices
        try:
            connected_devices = await usbmux.list_devices()
        except Exception:
            sysmsg = QCoreApplication.tr("If you are on Linux, make sure you have usbmuxd and libimobiledevice installed.")
            if os.name == 'nt':
                sysmsg = QCoreApplication.tr("Make sure you have the \"Apple Devices\" app from the Microsoft Store or iTunes from Apple's website.")
            _det.warning("usbmux.list_devices failed after %.2fs",
                         _time.monotonic() - _t0, exc_info=True)
            show_alert(ApplyAlertMessage(
                txt=QCoreApplication.tr("Failed to get device list. Click \"Show Details\" for the traceback.") + f"\n\n{sysmsg}", detailed_txt=str(traceback.format_exc())
            ))
            self.set_current_device(index=None)
            return
        _det.info("usbmux enumerated %d device(s) in %.2fs",
                  len(connected_devices), _time.monotonic() - _t0)
        if not connected_devices:
            # Nothing plugged in: leave an honest diagnostic note for the UI
            # instead of the old silent path (user could not tell a dead
            # Apple Mobile Device Service from "no cable").
            self.detection_notes.append(
                "No device reported by usbmux. Check the USB cable, tap "
                "Trust on the iPhone, and (on Windows) make sure the Apple "
                "Mobile Device Service is running (Apple Devices app or "
                "iTunes installed).")
        # Connect via usbmuxd — sequential per device (usually one).
        alerted = False
        for device in connected_devices:
            _td = _time.monotonic()
            try:
                # pair_timeout: detection must not sit up to 120s behind an
                # unanswered Trust prompt per device (lockdown_session
                # default). 30s is enough for a human tap; hitting Refresh
                # after trusting is instant.
                async with lockdown_session(device.serial, pair_timeout=30.0) as ld:
                    # SPEED: read the basic identity first and publish the
                    # device immediately. The old code started a whole
                    # Mobilebackup2 service session BEFORE collecting the
                    # name/version (seconds per device), and when backup
                    # encryption was on it dropped the device from the list
                    # entirely. The apply flow re-checks encryption itself
                    # before every restore, so detection no longer pays for
                    # or is gated by that check.
                    vals = ld.all_values
                    model = vals['ProductType']
                    hardware = vals['HardwareModel']
                    cpu = vals['HardwarePlatform']
                    try:
                        product_type = settings.value(device.serial + "_model", "", type=str)
                        hardware_type = settings.value(device.serial + "_hardware", "", type=str)
                        cpu_type = settings.value(device.serial + "_cpu", "", type=str)
                        if product_type == "":
                            # save the new product type
                            settings.setValue(device.serial + "_model", model)
                        else:
                            model = product_type
                        if hardware_type == "":
                            # save the new hardware model
                            settings.setValue(device.serial + "_hardware", hardware)
                        else:
                            hardware = hardware_type
                        if cpu_type == "":
                            # save the new cpu model
                            settings.setValue(device.serial + "_cpu", cpu)
                        else:
                            cpu = cpu_type
                    except Exception:
                        show_alert(ApplyAlertMessage(txt=QCoreApplication.tr("Click \"Show Details\" for the traceback."), detailed_txt=str(traceback.format_exc())))
                    dev = Device(
                            udid=device.serial,
                            usb=device.is_usb,
                            name=vals['DeviceName'],
                            version=vals['ProductVersion'],
                            build=vals['BuildVersion'],
                            model=model,
                            hardware=hardware,
                            cpu=cpu,
                            locale="",
                        )
                    self.devices.append(dev)
                    # Publish the first device right away — Home no longer
                    # waits for every remaining device / detail query.
                    if len(self.devices) == 1:
                        self.set_current_device(index=0)
                    if on_device_found is not None:
                        try:
                            on_device_found(dev)
                        except Exception:
                            _det.debug("on_device_found callback failed",
                                       exc_info=True)
                    # Details that only some pages need (locale for
                    # PosterBoard) are filled in afterwards, same session,
                    # so they never delay the device appearing.
                    try:
                        dev.locale = await ld.get_locale()
                    except Exception:
                        _det.debug("get_locale failed for %s", device.serial,
                                   exc_info=True)
                    _det.info(
                        "device %s ready in %.2fs (name=%r model=%s iOS %s build %s)",
                        device.serial, _time.monotonic() - _td,
                        dev.name, dev.model, dev.version, dev.build)
            except PasswordRequiredError as e:
                _det.warning("device %s needs Trust/unlock (%.2fs)",
                             device.serial, _time.monotonic() - _td)
                self.detection_notes.append(
                    "A connected device is locked or not trusted yet. "
                    "Unlock it, tap Trust, then press Refresh.")
                if not alerted:
                    alerted = True
                    show_alert(ApplyAlertMessage(txt=QCoreApplication.tr("Device is password protected! You must trust the computer on your device.\n\nUnlock your device. On the popup, click \"Trust\", enter your password, then try again.")))
            except MuxException as e:
                # there is probably a cable issue
                _det.warning("MuxException for %s after %.2fs: %r",
                             device.serial, _time.monotonic() - _td, e)
                self.detection_notes.append(
                    "USB connection error. Try a different cable or port.")
                if not alerted:
                    alerted = True
                    show_alert(ApplyAlertMessage(txt="MuxException: " + repr(e) + "\n\n" + QCoreApplication.tr("If you keep receiving this error, try using a different cable or port."),
                                   detailed_txt=str(traceback.format_exc())))
            except Exception as e:
                _det.warning("lockdown failed for %s after %.2fs: %r",
                             device.serial, _time.monotonic() - _td, e,
                             exc_info=True)
                self.detection_notes.append(
                    f"Could not read device info ({type(e).__name__}). "
                    "Unlock the device and press Refresh.")
                if not alerted:
                    alerted = True
                    show_alert(ApplyAlertMessage(txt=f"{type(e).__name__}: {repr(e)}", detailed_txt=str(traceback.format_exc())))

        if len(self.devices) > 0:
            self.set_current_device(index=0)
        else:
            self.set_current_device(index=None)
        _det.info("detection finished: %d device(s) in %.2fs total",
                  len(self.devices), _time.monotonic() - _t0)

    ## CURRENT DEVICE
    def set_current_device(self, index: int = None):
        if index == None or len(self.devices) == 0:
            self.data_singleton.current_device = None
            self.data_singleton.device_available = False
            self.data_singleton.gestalt_path = None
            clear_unsupported_mobilegestalt_state(mobilegestalt_decision("", ""))
            self.current_device_index = 0
        else:
            self.data_singleton.current_device = self.devices[index]
            dev = self.devices[index]
            # Support = build allowlist OR cable-reported iOS version in range
            # (user decision 2026-09-30: detect iOS from the cable too, not
            # only from the build number — RC variants and new patches keep
            # working even before their exact build is listed).
            if not is_device_supported(dev.build, dev.version):
                self.data_singleton.device_available = False
            else:
                self.data_singleton.device_available = True
            gestalt_decision = mobilegestalt_decision(dev.build, dev.version)
            if gestalt_decision.supported:
                # Nugget's gestalt flow: reuse the saved per-UDID MobileGestalt
                # copy when it still matches this device's build/model.
                if self.pref_manager.has_valid_mga_data(
                        self.get_current_device_udid(),
                        self.get_current_device_build(),
                        self.get_current_device_model()):
                    self.data_singleton.gestalt_path = self.data_singleton.SAVED_GESTALT_STRING
                else:
                    self.data_singleton.gestalt_path = None
            else:
                # Locked/unknown: no stale gestalt file or ON state from a
                # previous device may survive this selection.
                self.data_singleton.gestalt_path = None
                clear_unsupported_mobilegestalt_state(gestalt_decision)
            self.current_device_index = index
        
    def get_current_device_name(self) -> str:
        device = self.data_singleton.current_device
        return device.name if device != None else QCoreApplication.tr("No Device")

    def get_current_device_version(self) -> str:
        device = self.data_singleton.current_device
        return device.version if device != None else ""

    def get_current_device_build(self) -> str:
        device = self.data_singleton.current_device
        return device.build if device != None else ""

    def get_current_device_udid(self) -> Optional[str]:
        device = self.data_singleton.current_device
        return device.udid if device != None else None

    def get_current_device_model(self) -> str:
        device = self.data_singleton.current_device
        return device.model if device != None else ""

    def get_current_device_is_supported_by_fork(self) -> bool:
        device = self.data_singleton.current_device
        if device == None:
            return False
        return is_device_supported(device.build, device.version)

    def get_current_device_partially_supported(self) -> bool:
        """iOS 27 devices use the experimental three-phase protective restore."""
        device = self.data_singleton.current_device
        if device == None:
            return False
        try:
            return Version(device.version) >= Version("27.0")
        except Exception:
            return False
        
    # REAUDIT FIX: the sync wrapper reset_device_pairing() was dead code —
    # zero callers anywhere (grep); the only use is apply_worker.py calling
    # _reset_device_pairing() directly via asyncio.run. Removed the wrapper,
    # kept the implementation.
    async def _reset_device_pairing(self):
        # first, unpair it
        if self.data_singleton.current_device == None:
            return
        async with lockdown_session(self.data_singleton.current_device.udid) as ld:
            await ld.unpair()
            # next, pair it again
            await ld.pair()
        QMessageBox.information(
            None,
            QCoreApplication.tr("Pairing Reset"),
            QCoreApplication.tr("Your device's pairing was successfully reset. Refresh the device list before applying."))

    async def add_skip_setup(self, files_to_restore: list[FileToRestore], restoring_domains: bool):
        # TODO: Probably should move this to its own file
        # Build the cloud config with the same single-source builder that iOS 27
        # pushes natively (skip_all_setup27), so iOS 26's Phase 2 sparse restore
        # carries the byte-identical CloudConfigurationDetails.plist. On iOS 26
        # (MBDB sparse restore) every file is delivered through a real domain —
        # files with an empty domain are dropped during the restore. The
        # skip-setup plists always carry real domains, so they can always ride
        # the domain delivery on iOS 26, even when the selected tweaks are basic
        # plist tweaks that never set ``restoring_domains``.
        dev_version = self.get_current_device_version()
        if self.pref_manager.skip_setup and (restoring_domains
                or (dev_version and Version(dev_version) < Version("27.0"))):
            # get the already existing cloud config info
            async with lockdown_session(self.data_singleton.current_device.udid) as ld:
                async with MobileConfigService(lockdown=ld) as mcs:
                    existing = await mcs.get_cloud_configuration()
            cloud_config_plist = build_cloud_config(
                existing,
                supervised=self.pref_manager.supervised,
                organization_name=self.pref_manager.organization_name)
            # add the 2 skip setup files
            files_to_restore.append(FileToRestore(
                contents=plistlib.dumps(cloud_config_plist),
                restore_path="Library/ConfigurationProfiles/CloudConfigurationDetails.plist",
                domain="SysSharedContainerDomain-systemgroup.com.apple.configurationprofiles"
            ))
            purplebuddy_plist: dict = {
                "SetupDone": True,
                "SetupFinishedAllSteps": True,
                "UserChoseLanguage": True
            }
            files_to_restore.append(FileToRestore(
                contents=plistlib.dumps(purplebuddy_plist),
                restore_path="mobile/com.apple.purplebuddy.plist",
                domain="ManagedPreferencesDomain"
            ))

    def get_domain_for_path(self, path: str) -> str:
        # REAUDIT FIX: the old `owner` parameter was silently ignored (never
        # used in the body) and the comment below had the return order
        # backwards. Returns (relative_path, domain).
        from src.restore.path_mapping import split_path_into_domain

        mobile_domain, rel_path = split_path_into_domain(path)
        if mobile_domain is None:
            return path, ""
        return rel_path, mobile_domain
    
    def concat_file(self, contents: str, path: str, files_to_restore: list[FileToRestore], owner: int = 501, group: int = 501):
        # TODO: try using inodes here instead
        file_path, domain = self.get_domain_for_path(path)
        files_to_restore.append(FileToRestore(
            contents=contents,
            restore_path=file_path,
            domain=domain,
            owner=owner, group=group
        ))
    
    ## APPLYING OR REMOVING TWEAKS AND RESTORING
    def _raise_if_unsupported(self):
        if not self.get_current_device_is_supported_by_fork():
            raise NuggetException(QCoreApplication.tr(
                "This iOS version is not supported by this fork.\n\n"
                "WorkSlop Desktop supports iOS 16.0 -> 27.x (detected from "
                "the device over the cable). Please use the original Nugget "
                "for other versions."))

    def get_current_mobilegestalt_decision(self):
        """Shared MobileGestalt decision for the selected device.

        Build evidence is authoritative; version is only a fallback when
        the build is unknown, and no device is fail-closed (unknown).
        """
        device = self.data_singleton.current_device
        if device == None:
            return mobilegestalt_decision("", "")
        return mobilegestalt_decision(device.build, device.version)

    def get_current_device_is_gestalt_supported(self) -> bool:
        """True only when the shared MobileGestalt decision is supported."""
        return self.get_current_mobilegestalt_decision().supported

    def apply_gestalt_tweaks(self, update_label=lambda x: None, show_alert=lambda x: None):
        asyncio.run(self._apply_gestalt_tweaks(update_label, show_alert))

    def _load_gestalt_plist(self, update_label=lambda x: None):
        """Load + validate the device's MobileGestalt base plist.

        Shared by the MobileGestalt page flow and the main Apply pass (K3):
        gestalt tweaks patch CacheExtra/CacheData inside the *device's own*
        plist, so there must be a user-provided (or saved) base file.
        Raises NuggetException with a clear message instead of silently
        skipping the tweaks.
        """
        udid = self.get_current_device_udid()
        update_label(QCoreApplication.tr("Loading MobileGestalt file..."))
        gestalt_plist = None
        if self.data_singleton.gestalt_path is not None:
            if self.data_singleton.gestalt_path == self.data_singleton.SAVED_GESTALT_STRING:
                gestalt_plist = self.pref_manager.get_mga_data(udid)
            else:
                with open(self.data_singleton.gestalt_path, 'rb') as in_fp:
                    gestalt_plist = plistlib.load(in_fp)
        if gestalt_plist is None:
            raise NuggetException(QCoreApplication.tr(
                "No mobilegestalt file provided! Please select your device's "
                "com.apple.MobileGestalt.plist file first (MobileGestalt menu)."))
        if not self.pref_manager.is_valid_mga_plist(
                gestalt_plist, self.get_current_device_build(),
                self.get_current_device_model()):
            raise NuggetException(QCoreApplication.tr(
                "The MobileGestalt file does not match this device "
                "(build/model mismatch). Please provide the file from "
                "this exact device."))
        return gestalt_plist

    async def _apply_gestalt_tweaks(self, update_label=lambda x: None, show_alert=lambda x: None):
        """Apply only the MobileGestalt tweaks (Nugget's gestalt flow).

        Build rule (user decision 2026-09-30): gestalt tweaks are only
        applied on iOS 16.0 -> iOS 26.2 beta 1 builds. The device's own
        com.apple.MobileGestalt.plist (provided by the user, Nugget's
        "Getting the File" flow) is modified in CacheExtra/CacheData and
        restored to the mga location.
        """
        build = self.get_current_device_build()
        device = self.data_singleton.current_device
        version = device.version if device != None else ""
        decision = mobilegestalt_decision(build, version)
        if not decision.supported:
            cleared = clear_unsupported_mobilegestalt_state(decision)
            if cleared:
                log_warn("Cleared unsupported MobileGestalt tweak state: "
                         + ", ".join(sorted(cleared)))
            raise NuggetException(QCoreApplication.tr(
                "MobileGestalt tweaks are not supported on this device.\n\n")
                + decision.user_message)
        udid = self.get_current_device_udid()
        if not udid:
            raise NuggetException(QCoreApplication.tr("No device selected."))

        # B20 FIX: figure out WHAT is enabled before touching the MGA base
        # file. The RDAR fix writes a standalone resolution plist — it does
        # not need the MobileGestalt base at all. The old code loaded the MGA
        # file unconditionally, so an RDAR-only apply failed with "No
        # mobilegestalt file provided!" and needlessly rewrote the MGA plist.
        gestalt_tweak_types = (
            MobileGestaltTweak, MobileGestaltPickerTweak,
            MobileGestaltMultiTweak, MobileGestaltCacheDataTweak,
        )
        has_gestalt = any(
            isinstance(tw, gestalt_tweak_types) and tw.enabled
            for tw in tweaks.values()
        )
        if len(CustomGestaltTweaks.custom_tweaks) > 0:
            # Wave 10 Package 1: CustomGestaltTweaks is killed as a product
            # surface. Stale in-memory custom keys are ignored here and never
            # become CacheExtra payload, even on a MobileGestalt-supported
            # device.
            log_warn("CustomGestaltTweaks ignored: killed Wave 10 product "
                     "surface; no custom CacheExtra payload was generated.")
        # B20 FIX (continued): the RDAR fix switch lives on the MobileGestalt
        # page but this button ignored it. Honor it here too.
        rdar_tweak = tweaks.get(TweakID.RdarFix)
        rdar_on = rdar_tweak is not None and rdar_tweak.enabled
        if not has_gestalt and not rdar_on:
            raise NuggetException(QCoreApplication.tr(
                "No MobileGestalt tweaks are enabled."))

        update_label(QCoreApplication.tr("Applying MobileGestalt tweaks..."))
        files_to_restore: list[FileToRestore] = []
        if has_gestalt:
            gestalt_plist = self._load_gestalt_plist(update_label)
            for tweak_name in tweaks:
                tweak = tweaks[tweak_name]
                if isinstance(tweak, gestalt_tweak_types):
                    gestalt_plist = tweak.apply_tweak(gestalt_plist)
            self.concat_file(
                contents=plistlib.dumps(gestalt_plist),
                path=FileLocation.mga.value,
                files_to_restore=files_to_restore,
                owner=501, group=501,
            )
        if rdar_on:
            rdar_plist = rdar_tweak.apply_tweak({})
            rdar_payload = rdar_plist.get(rdar_tweak.file_location)
            if rdar_payload is not None:
                self.concat_file(
                    contents=plistlib.dumps(rdar_payload),
                    path=rdar_tweak.file_location.value,
                    files_to_restore=files_to_restore,
                    owner=501, group=501,
                )

        self.update_label = update_label
        self.do_not_unplug = ""
        if self.data_singleton.current_device.connected_via_usb:
            self.do_not_unplug = "\n" + QCoreApplication.tr("DO NOT UNPLUG")
        async with lockdown_session(udid) as ld:
            update_label(QCoreApplication.tr("Preparing to restore...") + self.do_not_unplug)
            await restore_files(
                files=files_to_restore, reboot=self.pref_manager.auto_reboot,
                lockdown_client=ld,
                progress_callback=self.progress_callback,
                backup_password="",
                # Nugget's gestalt flow restores the file directly: no
                # GoldenNugget protective backup here.
                skip_protective_backup=True,
            )
        msg = QCoreApplication.tr("Your device will now restart.\n\nRemember to turn Find My back on!")
        if not self.pref_manager.auto_reboot:
            msg = QCoreApplication.tr("Please restart your device to see changes.")
        return ApplyAlertMessage(txt=QCoreApplication.tr("All done! ") + msg, title=QCoreApplication.tr("Success!"), icon=QMessageBox.Information)

    async def start_restore(self, files_to_restore: list[FileToRestore], update_label=lambda x: None, backup_password: str = "", prepared_backup_root: str = None, skip_protective_backup: bool = False, include_keychain: bool = False, prompt_choice=None, supervised: bool = False, organization_name: str = ""):
        # hard-block any restore on an unsupported (old) iOS version
        self._raise_if_unsupported()
        self.update_label = update_label
        self.do_not_unplug = ""
        if self.data_singleton.current_device.connected_via_usb:
            self.do_not_unplug = "\n" + QCoreApplication.tr("DO NOT UNPLUG")
        # Use manual try/finally instead of async with so that ld.close()
        # errors (e.g. ConnectionTerminatedError after device reboot) do not
        # propagate as a misleading "Connection Lost" error to the UI.
        # lockdown_session suppresses close() errors the same way.
        async with lockdown_session(self.data_singleton.current_device.udid) as ld:
            update_label(QCoreApplication.tr("Preparing to restore...") + self.do_not_unplug)
            await restore_files(
                files=files_to_restore, reboot=self.pref_manager.auto_reboot,
                lockdown_client=ld,
                progress_callback=self.progress_callback,
                backup_password=backup_password,
                prepared_backup_root=prepared_backup_root,
                skip_protective_backup=skip_protective_backup,
                include_keychain=include_keychain,
                prompt_choice=prompt_choice,
                afc_media=afc_media_enabled(self.pref_manager.use_afc_media),
                supervised=supervised,
                organization_name=organization_name,
            )
            tweaks[TweakID.PosterBoard].config_manager.save_staged_ids(self.get_current_device_udid())
            if tweaks[TweakID.PosterBoard].full_reset:
                # the on-device PosterBoard container was wiped — the stale
                # locally-saved database and wallpaper IDs no longer match the
                # empty DB, so drop them or the next apply rebuilds ghosts.
                PreferenceManager.remove_pbconfig_data(self.get_current_device_udid())
                tweaks[TweakID.PosterBoard].config_manager.saved_items = []
                tweaks[TweakID.PosterBoard].config_manager.database = None
                tweaks[TweakID.PosterBoard].config_manager.staged_database = None
                tweaks[TweakID.PosterBoard].resetModes = []
                tweaks[TweakID.PosterBoard].full_reset = False
            msg = QCoreApplication.tr("Your device will now restart.\n\nRemember to turn Find My back on!")
            if not self.pref_manager.auto_reboot:
                msg = QCoreApplication.tr("Please restart your device to see changes.")
            return ApplyAlertMessage(txt=QCoreApplication.tr("All done! ") + msg, title=QCoreApplication.tr("Success!"), icon=QMessageBox.Information)

    def progress_callback(self, progress):
        if self.update_label == None:
            return
        if isinstance(progress, str):
            self.update_label(progress)
            return
        prog = ""
        if progress != None:
            prog = f" ({progress:6.1f}% )"
        self.update_label(QCoreApplication.tr("Restoring to device...{0}{1}").format(prog, self.do_not_unplug))
    def _backup_progress(self, update_label):
        """Progress callback for the pre-restore device backups.

        Unlike ``progress_callback`` it does not depend on ``self.update_label``
        (only set by ``start_restore``), so it is safe to call before any
        restore has started. Status strings pass through as labels; anything
        that is not a number is dropped so the bar never sees garbage.
        """
        def _cb(progress):
            if isinstance(progress, str):
                update_label(progress)
                return
            if isinstance(progress, bool) or not isinstance(progress, (int, float)):
                return
            update_label(QCoreApplication.tr("Backing up device... ({0:.1f}%)").format(progress))
        return _cb
    def apply_changes(self, update_label=lambda x: None, show_alert=lambda x: None, prompt_password=None, prompt_choice=None, on_backup_complete=None):
        asyncio.run(self._apply_changes(update_label, show_alert, prompt_password, prompt_choice, on_backup_complete))
    async def _apply_changes(self, update_label=lambda x: None, show_alert=lambda x: None, prompt_password=None, prompt_choice=None, on_backup_complete=None):
        files_to_restore: list[FileToRestore] = []
        final_alert = None
        pb = tweaks[TweakID.PosterBoard]
        original_tendies = list(pb.tendies)
        try:
            self._raise_if_unsupported()
            # Wave 10 Apply Journal: begin the durable per-tweak record for
            # this operation (finalized by the tweak pass, or below on the
            # early-return/abort paths). Never read by the restore path.
            self.last_apply_journal_path = None
            self._journal_error = None
            self._current_journal = begin_journal(
                "apply", device=self._journal_device_info())
            update_label(QCoreApplication.tr("Applying changes to files..."))
            self._protective_backup_skipped = False
            self._known_backup_encryption = None  # re-established by Phase 0
            # B1: merge base for the iOS 27 HomeDomain .GlobalPreferences.plist
            # write. Filled by _register_gp_base during Phase 0; None means
            # "no base" -> the HomeDomain copy must NOT be written (writing a
            # tweak-only dict would wipe the user's language/region/keyboard).
            self._gp_base_plist = None

            # iOS 26.2+ (iOS 27 era) uses the heavy three-phase protective restore
            # B23 FIX: never silently drop tendies. Truncating without telling
            # the user meant wallpapers vanished with no explanation. The
            # message is kept in tendie_warn so it can be appended to the
            # final user-facing alert below (log_warn alone is invisible).
            tendie_warn = None
            if len(original_tendies) > MAX_TENDIES_PER_RESTORE:
                tendie_warn = (
                    f"Only {MAX_TENDIES_PER_RESTORE} PosterBoard wallpapers can be applied "
                    f"per restore — {len(original_tendies) - MAX_TENDIES_PER_RESTORE} were skipped "
                    f"(remove some and apply again to include them).")
                log_warn(tendie_warn)
            pb.tendies = original_tendies[:MAX_TENDIES_PER_RESTORE]

            # B24 FIX: only PosterBoard-targeting templates need the PosterBoard
            # database machinery. Any template used to trigger it, churning
            # the PB sqlite (fetch + modify + restore) for templates that
            # never touch PosterBoard.
            _templates_tweak = tweaks[TweakID.Templates]
            _pb_templates = [t for t in _templates_tweak.templates
                             if getattr(t, "domain", "") == "AppDomain-com.apple.PosterBoard"]
            needs_posterboard = not (
                len(pb.tendies) == 0 and pb.videoFile is None
                and len(_pb_templates) == 0)
            log_info(f'needs_posterboard={needs_posterboard}, tendies={len(pb.tendies)}, videoFile={pb.videoFile is not None}')

            # Phase 0: protective backup.
            #  - iOS 27+ (partial support): the heavy backup is built and later
            #    restored (Phase 1/3) to survive the security-recovery wipe. It
            #    also carries the PosterBoard sqlite when wallpapers are pending.
            #  - iOS 26.x: the apply is a plain sparse restore (no wipe, no Phase
            #    3), so NO Phase 0 runs here at all — PosterBoard delivery
            #    happens through the targeted PosterBoard-only backup below.
            prepared_root = None
            pb_from_cache = False
            # Kill-switch env (new name; legacy GOLDENNUGGET_* still honored).
            raw_sparse = (os.environ.get("WORKSLOP_NO_PROTECTIVE_BACKUP") == "1"
                          or os.environ.get("GOLDENNUGGET_NO_PROTECTIVE_BACKUP") == "1")
            if raw_sparse:
                # Kill switch: straight raw sparse pass, no protective backup at
                # any phase. The whole Phase 0 is skipped — no live backup, no
                # cache, no PosterBoard delivery. Flip everything below to the
                # no-protection path.
                log_warn("WORKSLOP_NO_PROTECTIVE_BACKUP=1 — raw sparse: "
                         "skipping Phase 0 protective backup entirely "
                         "(no data protection)")
                self._protective_backup_skipped = True
            partially_supported = self.get_current_device_partially_supported()
            should_prepare = partially_supported and not raw_sparse
            if should_prepare:
                # On NotEnoughDiskSpaceError the user can choose to continue
                # without it — tweaks still apply, but there is no data
                # protection (photos/settings get wiped).
                try:
                    prepared_root, pb_from_cache = await self._prepare_protective_backup(
                        update_label, needs_posterboard=needs_posterboard,
                        prompt_password=prompt_password, on_backup_complete=on_backup_complete)
                except Exception as e:
                    if "disk space" in str(e).lower() or "NotEnoughDiskSpace" in type(e).__name__:
                        # The Yes/No decision must be asked on the main thread
                        # (this runs on ApplyThread — a QMessageBox here is a
                        # cross-thread-widget bug). Relay via ``prompt_choice``;
                        # "resume" == continue without protection, "abort" ==
                        # refuse. Without a callback (headless) default to abort.
                        if prompt_choice is None:
                            log_warn("Protective backup failed (disk space) and no "
                                     "prompt_choice callback — aborting apply")
                            return
                        decision = prompt_choice(
                            QCoreApplication.tr("Not Enough Disk Space"),
                            QCoreApplication.tr(
                                "The protective backup failed because the device or "
                                "computer does not have enough free disk space.\n\n"
                                "Continue anyway WITHOUT data protection?\n"
                                "(Photos, settings and app data may be lost.)"))
                        if decision == "resume":
                            log_warn("User chose to continue without protective backup")
                            prepared_root = None
                            pb_from_cache = False
                            self._protective_backup_skipped = True
                        else:
                            return
                    else:
                        raise
            else:
                log_info("Phase 0 skipped: no iOS 27 protective restore required")

            # PosterBoard delivery:
            #  - iOS 27+: the sqlite normally rides the Phase 0 backup (extracted
            #    inside _prepare_protective_backup); when it could not be read out
            #    of it (device rejected the container / encrypted backup), this
            #    targeted PosterBoard-only backup runs as the fallback.
            #  - iOS 26.x: no Phase 0 at all, so this targeted backup IS the
            #    delivery channel — tiny and fast, no full device backup.
            if needs_posterboard and not pb_from_cache and not raw_sparse:
                if os.environ.get("GOLDENNUGGET_SKIP_PB_BACKUP"):
                    log_warn("GOLDENNUGGET_SKIP_PB_BACKUP=1 set; skipping PosterBoard DB fetch")
                else:
                    await self._backup_posterboard_database(update_label, force=True)

            self._apply_hotload_daemon_forcing()

            final_alert, files_to_restore = await self._apply_tweak_pass(
                update_label,
                templates=tweaks[TweakID.Templates].templates,
                prepared_backup_root=prepared_root,
                prompt_password=prompt_password,
                prompt_choice=prompt_choice,
                skip_protective_backup=self._protective_backup_skipped,
            )
            # Record what just got applied so a later "unchanged tweaks +
            # added wallpapers only" apply can skip the Phase 2 sparse pass.
            from src.restore.lastapply import sparse_signature, write_lastapply
            udid = self.get_current_device_udid()
            if udid:
                write_lastapply(udid, sparse_signature(files_to_restore))
            update_label(QCoreApplication.tr("Success!"))
            # B23: surface the tendie truncation in the user-facing result
            # alert — a log line alone never reaches the user.
            if tendie_warn and final_alert is not None:
                final_alert.txt = f"{final_alert.txt}\n\n{tendie_warn}"
        except Exception as e:
            self._journal_error = f"{type(e).__name__}: {e}"
            final_alert = show_apply_error(e, update_label, files_list=files_to_restore)
        finally:
            journal = getattr(self, "_current_journal", None)
            if journal is not None and not journal.finalized:
                # The tweak pass finalizes the paths it owns; reaching this
                # point unfinalized means the operation stopped before or
                # outside the pass (early abort vs. hard failure).
                self._finish_journal(
                    journal,
                    "failed" if self._journal_error else "aborted",
                    error=self._journal_error)
            self._current_journal = None
            pb.tendies = original_tendies
            show_alert(final_alert)

    # -- Wave 10 Apply Journal helpers ------------------------------------
    def _journal_device_info(self) -> dict:
        return {
            "name": self.get_current_device_name(),
            "model": self.get_current_device_model(),
            "ios": self.get_current_device_version(),
            "build": self.get_current_device_build(),
            "udid": self.get_current_device_udid(),
        }

    def _finish_journal(self, journal, status, error=None) -> None:
        if journal is None or journal.finalized:
            return
        try:
            journal.finalize(status, error=error)
            self.last_apply_journal_path = journal.path
            log_info(f"APPLY_JOURNAL operation_id={journal.operation_id} "
                     f"mode={journal.mode} status={status} "
                     f"tweaks={len(journal.data['tweaks'])} path={journal.path}")
        except Exception as e:
            log_warn(f"Apply Journal finalize failed: {e}")

    def _journal_describe(self, journal, tweak_name, tweak) -> list:
        """Build the journal entry (or entries) for one requested tweak.

        Descriptor resolution: registry spec first, then the Status Bar
        operation descriptors, then MobileGestalt classes, then a marked
        fallback so no enabled tweak ever lacks an entry.
        """
        name = tweak_name.name if hasattr(tweak_name, "name") else str(tweak_name)

        def base():
            return {
                "tweak_id": name,
                "requested": True,
                "source": ("hotload" if (tweak_name == TweakID.Daemons
                                         and self._hotload_forced_daemon_keys)
                           else "tweak_state"),
                "compatibility": {"result": "compatible", "reason": None},
                "hotload": {"result": "allowed", "reason": None},
            }

        if isinstance(tweak, StatusBarTweak):
            entries = []
            try:
                ops = tweak.describe_active_operations()
            except Exception:
                ops = []
            if not ops:
                ops = [{"id": "statusbar.overrides", "name": "Status Bar",
                        "family": "Status Bar", "count": 0}]
            for op in ops:
                entry = base()
                entry.update({
                    "id": op.get("id"),
                    "name": op.get("name"),
                    "family": op.get("family", "Status Bar"),
                    "kind": "special",
                    "operation": {k: v for k, v in op.items()
                                  if k not in ("id", "name", "family")},
                })
                entries.append(journal.add_entry(entry))
            return entries

        canonical = canonical_tweak_id(tweak_name)
        spec = SPECS_BY_ID.get(canonical)
        if spec is not None:
            entry = base()
            if isinstance(tweak, AdvancedPlistTweak):
                kind = "advanced"
                operation = {"location": spec.location.value, "keys": []}
            elif isinstance(tweak, FeatureFlagTweak):
                kind = "feature_flag"
                operation = {"location": spec.location.value,
                             "key": spec.key}
            else:
                kind = "plist"
                operation = {
                    "location": spec.location.value,
                    "key": spec.key,
                    "value": value_summary(
                        getattr(tweak, "value", spec.value),
                        sensitive=(spec.kind == _SpecKind.TEXT)),
                }
            entry.update({"id": name, "name": spec.title,
                          "family": spec.section.value, "kind": kind,
                          "operation": operation})
            return [journal.add_entry(entry)]

        if isinstance(tweak, (MobileGestaltTweak, MobileGestaltPickerTweak,
                              MobileGestaltMultiTweak,
                              MobileGestaltCacheDataTweak)):
            operation = {}
            if getattr(tweak, "key", None):
                operation["cache_extra_key"] = tweak.key
            if getattr(tweak, "subkey", None):
                operation["subkey"] = tweak.subkey
            entry = base()
            entry.update({"id": f"tweakid.{name.lower()}", "name": name,
                          "family": "MobileGestalt", "kind": "special",
                          "operation": operation})
            return [journal.add_entry(entry)]

        entry = base()
        entry.update({"id": f"tweakid.{name.lower()}", "name": name,
                      "family": type(tweak).__name__, "kind": "special",
                      "descriptor_missing": True, "operation": {}})
        return [journal.add_entry(entry)]

    def _journal_attach(self, journal, side: dict) -> None:
        """Attach staged files to entries and resolve pre-restore states.

        ``side`` carries generation-time associations keyed by id(entry):
        ``slices`` [(start, end) index ranges into files_to_restore],
        ``plist`` (FileLocation, contributed keys), and ``bookrestore``
        (tweak names whose only payload route was skipped).
        """
        slices = side.get("slices", {})
        plist_assoc = side.get("plist", {})
        bookrestore = side.get("bookrestore", set())
        for entry in journal.data["tweaks"]:
            for start, end in slices.get(id(entry), []):
                keys = [journal.key_for_index(i)
                        for i in range(start, end)]
                journal.associate(entry, [k for k in keys if k])
            assoc = plist_assoc.get(id(entry))
            if assoc is not None:
                location, keys = assoc
                rel_path, domain = self.get_domain_for_path(location.value)
                candidate = f"{domain}/{rel_path.lstrip('/')}"
                if candidate in journal._file_keys:
                    journal.associate(entry, [candidate])
                if entry.get("kind") == "advanced":
                    entry["operation"]["keys"] = sorted(keys)
            if entry["status"] != "requested":
                continue
            if entry["files"]:
                entry["status"] = TW_STAGED
            elif entry["tweak_id"] in bookrestore:
                entry["status"] = TW_SKIPPED
                entry["skip_reason"] = "bookrestore_unsupported"
            elif entry.get("operation", {}).get("no_file_reason"):
                entry["status"] = TW_SKIPPED
                entry["skip_reason"] = entry["operation"]["no_file_reason"]
            else:
                entry["status"] = TW_FAILED
                entry["error"] = "no_file_staged"

    def _apply_hotload_daemon_forcing(self):
        """HotLoad "disable_daemon" rules: force their daemons into the
        disabled-daemons plist for this exact apply, regardless of the UI
        toggles or whatever a loaded preset said. Runs right before the
        tweak pass so the forced keys ride along with every apply."""
        try:
            dm_settings = getattr(getattr(self, "pref_manager", None), "settings", None)
            hotload = HotLoad(dm_settings)
            forced = hotload.disabled_daemon_keys(
                device_version=self.get_current_device_version(),
                device_model=self.get_current_device_model())
            self._hotload_forced_daemon_keys = set(forced)
            if not forced:
                return
            from src.tweaks.tweak_loader import load_daemons
            load_daemons()
            daemons_tweak = tweaks.get(TweakID.Daemons)
            if daemons_tweak is None:
                return
            # Safety rules are authoritative: the forced keys must reach the
            # plist regardless of the interface whitelist (a rule may name a
            # daemon with no UI switch, e.g. ScreenTime). Extend allowed_keys
            # so set_multiple_values and the apply-pass filter both let them
            # through, then toggle them on.
            daemons_tweak.allowed_keys.update(forced)
            daemons_tweak.set_multiple_values(sorted(forced), value=True)
            # B12 FIX: the forced keys were silently dead — AdvancedPlistTweak.
            # apply_tweak early-returns when the tweak is not enabled, so the
            # keys set above never reached the device. Enabling the tweak
            # makes the forcing real.
            daemons_tweak.set_enabled(True)
            log_info(f"[HotLoad] daemons force-disabled by safety rules: "
                     f"{', '.join(sorted(forced))}")
        except Exception as e:
            log_warn(f"[HotLoad] daemon forcing failed: {e}")

    async def _prepare_protective_backup(self, update_label=lambda x: None,
                                         needs_posterboard: bool = False,
                                         prompt_password=None, on_backup_complete=None) -> tuple:
        """Phase 0: build the protective backup that Phase 3 will restore.

        Wraps ``_build_protective_backup`` and refuses to hand back a backup that
        has no verified copy of the photos. See that method for the two modes;
        this wrapper exists so the media gate cannot be bypassed by one of the
        several return paths inside it.
        """
        prepared, pb_ok = await self._build_protective_backup(
            update_label, needs_posterboard, prompt_password, on_backup_complete)
        self._require_media_copy(prepared)
        return prepared, pb_ok

    @staticmethod
    def _require_media_copy(prepared) -> None:
        """Abort before the wipe if the photos are not safely on this computer.

        When the AFC media channel carries the bulk photo trees, those trees are
        NOT in the backup — the media store is their only copy once the device
        is wiped. An unverified store (never pulled, interrupted pull, cancelled
        parallel task) must stop the apply here, while the device is still
        intact, instead of letting Phase 5 push a fragment and report success.
        """
        media_src = getattr(prepared, "media_src", "") if prepared else ""
        if not media_src:
            return
        if media_store_verified(media_src):
            return
        raise NuggetException(
            f"The photos/videos could not be fully backed up "
            f"({describe_media_store(media_src)}). Applying tweaks would wipe "
            f"the device with no complete copy of the media, so it was stopped "
            f"before anything was changed. Free up disk space / reconnect the "
            f"device and try again; the backup cache can also be refreshed from "
            f"the pre-apply summary.")

    async def _build_protective_backup(self, update_label=lambda x: None,
                                        needs_posterboard: bool = False,
                                        prompt_password=None, on_backup_complete=None) -> tuple:
        """Build the protective backup (LIVE or cached master) — see above.
    
        Two modes:

        * LIVE (default): runs a fresh ``perform_protective_backup`` right now,
          always including the PosterBoard container when wallpapers are being
          applied — so ``extract_posterboard_db`` yields the fresh sqlite and the
          config manager builds new wallpapers on top of the current on-device
          state. No caching involved.
    
        * CACHE (EXPERIMENTAL, off by default): reuses/refreshes the persistent
          per-device master ("Use Fast Backup Cache (Experimental)" in Settings).
          When wallpapers are applied the master ALWAYS refreshes first — the
          "reuse as-is" fast path only applies when nothing is pending — so the
          extracted DB is never a stale copy.
    
Returns (PreparedBackup, posterboard_db_ok). When the PosterBoard
        container cannot be read out of the backup the caller falls back to the
        targeted ``_backup_posterboard_database``. Returns (None, False)
        only when there is no UDID at all.

        iOS 26 applies never take this path: their restore is a plain sparse
        pass, so the heavy backup serves no purpose there — PosterBoard
        delivery goes through ``_backup_posterboard_database`` instead.
        """
        udid = self.get_current_device_udid()
        if not udid:
            return None, False
    
        from src.restore.protective import (
            PreparedBackup, extract_gp_base_plist, extract_posterboard_db, is_backup_encrypted,
            new_protective_backup_dir, perform_protective_backup,
            prune_protective_backups)
    
        def _register_pb_db(backup_root: str) -> bool:
            """Extract the fresh PosterBoard sqlite and register it for editing.
    
            Returns False (so the legacy separate backup still runs) when the
            container is missing from the backup or the DB is unusable.
            """
            if not needs_posterboard or os.environ.get("GOLDENNUGGET_SKIP_PB_BACKUP"):
                return True
            import tempfile as _tempfile
            with _tempfile.TemporaryDirectory(prefix="nugget_pbdb_") as tmp_dir:
                db_path_and_version = extract_posterboard_db(
                    backup_root, udid, os.path.join(tmp_dir, "posterboard.sqlite3"))
                if db_path_and_version is None:
                    log_warn("PosterBoard DB missing from the protective backup — "
                             "falling back to a separate backup")
                    return False
                db_path, structure_version = db_path_and_version
                pb = tweaks[TweakID.PosterBoard]
                try:
                    if not pb.config_manager.update_database_file(
                            db_path, udid, structure_version=structure_version):
                        raise NuggetException("The PosterBoard database is not of the correct format!")
                    pb.config_manager.update_for_saved_database(udid)
                    update_label(QCoreApplication.tr("PosterBoard database backed up successfully."))
                except NuggetException as e:
                    log_warn(f"PosterBoard DB unusable ({e}) — falling back to a separate backup")
                    return False
            return True

        def _register_gp_base(backup_root: str) -> None:
            """B1: extract the live .GlobalPreferences.plist from the Phase 0
            master backup as the merge base for the iOS 27 HomeDomain write.
            Must run here — clean_backup_for_restore prunes this file from the
            restore copy later. Leaves self._gp_base_plist as None when the
            base cannot be obtained; the apply pass then skips the HomeDomain
            write instead of wiping the user's settings with a tweak-only
            dict.
            """
            self._gp_base_plist = None
            gp_base_recorded = False
            try:
                import tempfile as _tf
                with _tf.TemporaryDirectory(prefix="nugget_gpbase_") as tmp_dir:
                    dest = os.path.join(tmp_dir, "GlobalPreferences.plist")
                    extracted = extract_gp_base_plist(backup_root, udid, dest)
                    if extracted is None:
                        return
                    with open(extracted, "rb") as f:
                        base = plistlib.load(f)
                    if not isinstance(base, dict):
                        log_warn("GP base plist is not a dict — ignoring it")
                        return
                    self._gp_base_plist = base
                    # Persist the pristine base for the reset flow: reset runs
                    # in a later session and must restore this file instead of
                    # nulling it (nulling would wipe the user's language /
                    # region / keyboard on iOS 27).
                    from src.restore.lastapply import write_gp_base
                    write_gp_base(udid, base)
                    gp_base_recorded = True
                    log_info(f"GP merge base loaded ({len(base)} keys) for the iOS 27 HomeDomain write")
            except Exception as e:
                log_warn(f"Could not load .GlobalPreferences.plist merge base: {e}")
                self._gp_base_plist = None
                # Don't leave a half-written record behind.
                if not gp_base_recorded:
                    try:
                        from src.restore.lastapply import clear_gp_base
                        clear_gp_base(udid)
                    except Exception:
                        pass
    
        async def _live_backup(lc) -> tuple:
            """Fresh protective backup (no cache) with the PosterBoard container
            riding along whenever wallpapers are about to be applied.

            When the AFC media channel is enabled (``use_afc_media`` pref,
            off via ``GOLDENNUGGET_NO_AFC_MEDIA=1``), photos/videos are pulled
            over AFC in parallel with the mobilebackup2 backup; the backup then
            carries only the non-media protective scope. Either way the media
            dir is recorded on the PreparedBackup so Phase 3 pushes it back.
            """
            # Persistent, one directory per run. Once Phase 2 wipes the device
            # this backup is the ONLY copy of the user's photos, Apple ID and
            # settings, so it must survive a reboot and must never be swept as
            # a temp leftover. A fresh directory per run also means a failed
            # backup cannot damage the previous run's copy.
            backup_root = new_protective_backup_dir(udid)
            use_afc_media = afc_media_enabled(self.pref_manager.use_afc_media)
            update_label(QCoreApplication.tr("Backing up device..."))
            # include_keychain is left None (auto) so it follows the device's
            # live encryption state — one less round-trip before the backup.
            try:
                is_encrypted = await perform_protective_backup(
                    lc, backup_root, progress_callback=self._backup_progress(update_label),
                    include_photos=True, include_posterboard=needs_posterboard,
                    include_keychain=None, include_afc_media=use_afc_media)
            except Exception:
                # A failed run carries no/useless Manifest.db, so
                # list_protective_backups excludes it and prune would never
                # reclaim it — remove the partial dir right here.
                shutil.rmtree(backup_root, ignore_errors=True)
                raise
            # Only retire the previous run once this one is solid — pruning
            # early would delete the last good backup before the new run exists.
            prune_protective_backups(udid)
            self._known_backup_encryption = is_encrypted
            media_src = afc_media_dir_for(backup_root) if use_afc_media else ""
            log_info(f"Phase 0: live protective backup ready (always fresh; "
                     f"PosterBoard container {'included' if needs_posterboard else 'not needed'}; "
                     f"keychain {'included' if is_encrypted else 'excluded (backup not encrypted)'}; "
                     f"media via {'AFC' if use_afc_media else 'mobilebackup2'})")
            prepared = PreparedBackup(root=backup_root, manifest_password="",
                                      master=False, media_src=media_src)
            # WorkSlop: the live device backup just hit 100%. Record it and
            # hand it to the GUI (via on_backup_complete) so the file
            # manager can be opened with the finished backup selected.
            self.last_protective_backup_root = backup_root
            if on_backup_complete is not None:
                on_backup_complete(backup_root)
            # Register the GP merge base BEFORE any early return: an encrypted
            # backup simply yields no base (extract returns None gracefully),
            # but skipping registration here used to leave _gp_base_plist
            # unset on the needs_posterboard+encrypted path.
            _register_gp_base(backup_root)
            if needs_posterboard and is_encrypted:
                log_warn("Encrypted backup cannot yield a readable PosterBoard DB — "
                         "falling back to a separate backup")
                return prepared, False
            return prepared, _register_pb_db(backup_root)

        cache_enabled = (self.pref_manager.use_backup_cache
                         and not os.environ.get("GOLDENNUGGET_NO_BACKUP_CACHE"))

        async with lockdown_session(udid) as lc:
            if not cache_enabled:
                log_info("Protective backup cache is an experimental feature and is "
                         "off — running a fresh live protective backup instead")
                return await _live_backup(lc)

            # --- EXPERIMENTAL cache path ---
            use_afc_media = afc_media_enabled(self.pref_manager.use_afc_media)
            encrypted = await is_backup_encrypted(lc)
            self._known_backup_encryption = encrypted
            manifest_password = ""
            if encrypted:
                if prompt_password is None:
                    log_info("No password prompt available — bypassing the protective backup cache")
                    return await _live_backup(lc)
                update_label(QCoreApplication.tr("Backup encryption is enabled. Enter your backup password to use the fast cached backup:"))
                password = prompt_password(
                    QCoreApplication.tr("Backup Encryption Password"),
                    QCoreApplication.tr("Enter your iTunes/Finder backup password (used locally to prepare the cached backup):"))
                if not password:
                    log_info("No backup password provided — bypassing the protective backup cache")
                    return await _live_backup(lc)
                manifest_password = password
                self._backup_password = password  # reuse it for the Phase 3 restore prompt
            from src.restore.protective import CACHE_REFRESH_SECS, ProtectiveBackupCache
            cache = ProtectiveBackupCache(udid, product_version=self.get_current_device_version(),
                                          encrypted=encrypted)
            found = cache.locate()
            # "the folder is not empty" is not proof of a usable media copy: a
            # cancelled or interrupted pull leaves a partial tree that still has
            # files in it. Only a store whose last pull ran to completion counts
            # as in sync, so a partial one always forces a refresh (which redoes
            # the pull) instead of being carried into the wipe.
            media_ready = (not use_afc_media
                           or media_store_verified(str(cache.media_dir)))
            # fast path: a fresh cache (no wallpapers pending, media already in
            # sync) is reused as-is — no device session at all; past the TTL it
            # gets an incremental refresh. The AFC media store has to exist too,
            # or the refresh (which pulls the photos) is still needed.
            if found and not needs_posterboard and found["age_secs"] < CACHE_REFRESH_SECS and media_ready:
                log_info(f"Cache is {found['age_secs'] // 60} min old — reusing without a backup session")
                master_root = str(cache.master_root)
            else:
                update_label(QCoreApplication.tr("Backing up device (cached)..."))
                master_root = await cache.refresh(
                    lc, progress_callback=self._backup_progress(update_label),
                    include_photos=True, include_posterboard=needs_posterboard,
                    include_keychain=encrypted,
                    include_afc_media=use_afc_media)

            media_src = str(cache.media_dir) if use_afc_media else ""
            prepared = PreparedBackup(root=master_root, manifest_password=manifest_password,
                                      master=True, media_src=media_src)
            if needs_posterboard and encrypted:
                log_warn("Encrypted cache cannot yield a readable PosterBoard DB — "
                         "falling back to a separate backup")
                return prepared, False
            _register_gp_base(master_root)
            return prepared, _register_pb_db(master_root)

    async def refresh_backup_cache(self, update_label=lambda x: None) -> str:
        """Force a refresh of the backup cache master for the current device.

        Runs the same incremental master refresh + AFC media diff as an apply
        would, without applying any tweaks. Used by the pre-apply summary's
        "Update Cache" action so the user can freshen the cache (and from
        which date it will be reused) before confirming. Raises NuggetException
        when there is no device or the cache is disabled.
        """
        udid = self.get_current_device_udid()
        if not udid:
            raise NuggetException("No device selected.")
        cache_enabled = (self.pref_manager.use_backup_cache
                         and not os.environ.get("GOLDENNUGGET_NO_BACKUP_CACHE"))
        if not cache_enabled:
            raise NuggetException(
                "The backup cache is disabled. Enable 'Use Fast Backup Cache "
                "(Experimental)' in Settings → Backup first.")

        from src.restore.protective import (
            ProtectiveBackupCache, is_backup_encrypted)
        use_afc_media = afc_media_enabled(self.pref_manager.use_afc_media)
        async with lockdown_session(udid) as lc:
            encrypted = await is_backup_encrypted(lc)
            cache = ProtectiveBackupCache(udid,
                                          product_version=self.get_current_device_version(),
                                          encrypted=encrypted)
            update_label(QCoreApplication.tr("Updating backup cache..."))
            master_root = await cache.refresh(
                lc, progress_callback=self._backup_progress(update_label),
                include_photos=True, include_posterboard=False,
                include_keychain=encrypted,
                include_afc_media=use_afc_media)
            log_info(f"Backup cache refreshed for {udid}")
        return master_root

    async def _backup_posterboard_database(self, update_label=lambda x: None, force: bool = False):
        """Fetch the device's PosterBoard sqlite database before applying wallpapers.

        The database (PBFPosterExtensionDataStoreSQLiteDatabase.sqlite3) holds the
        user's current wallpapers. A fresh copy is pulled from the device every
        time a tendie is about to be applied (``force=True``) so the config
        manager always builds on top of the current on-device state. Previously
        fetched copies are only reused when the database is genuinely needed and
        a fresh one isn't required (``force=False``).

        Uses a targeted PosterBoard-only backup
        (``targeted_posterboard_database_backup`` in ``src/restore/posterboard_backup.py``):
        only the PosterBoard container is pulled off the device and everything
        else the device uploads is drained mid-stream, so no full backup is
        ever written. Failure is non-fatal: the apply continues and config mode
        surfaces its own clear error later.
        """
        udid = self.get_current_device_udid()
        if not udid:
            return
        # already backed up for this device and no fresh copy required -> reuse it
        if not force and PreferenceManager.has_pbconfig_data(udid):
            return
        pb = tweaks[TweakID.PosterBoard]
        if (len(pb.tendies) == 0 and pb.videoFile is None
                and len(tweaks[TweakID.Templates].templates) == 0):
            # no wallpapers being added, nothing to back up
            return

        update_label(QCoreApplication.tr("Fetching PosterBoard database..."))
        from src.restore.posterboard_backup import targeted_posterboard_database_backup
        try:
            db_result = await targeted_posterboard_database_backup(
                udid, update_label, self._backup_progress(update_label))
            if not db_result or not os.path.exists(db_result[0]):
                raise NuggetException("The PosterBoard database file doesn't exist!")
            db_file_path, structure_version = db_result
            update_label(QCoreApplication.tr("Saving PosterBoard database..."))
            if not pb.config_manager.update_database_file(
                    db_file_path, udid, structure_version=structure_version):
                raise NuggetException("The PosterBoard database is not of the correct format!")
            pb.config_manager.update_for_saved_database(udid)
            update_label(QCoreApplication.tr("PosterBoard database backed up successfully."))
        except Exception as e:
            log_error(f"Failed to back up PosterBoard database: {e}\n{traceback.format_exc()}")
            print(f"Failed to back up PosterBoard database: {e}")
            print(traceback.format_exc())
            if _is_device_locked_error(e):
                update_label(QCoreApplication.tr("Warning: could not back up PosterBoard database — device is locked. Please unlock your device and try again."))
            else:
                update_label(QCoreApplication.tr("Warning: could not back up the PosterBoard database automatically."))

    async def _apply_tweak_pass(self, update_label=lambda x: None, templates: list = None, prepared_backup_root=None, prompt_password=None, prompt_choice=None, skip_protective_backup: bool = False):
        """Generate all tweak files and restore them to the device in one pass.

        Returns (alert, files_to_restore) so the caller can surface the result
        and keep the file list for error reporting.
        """
        if templates is None:
            templates = tweaks[TweakID.Templates].templates
        # create the other plists
        flag_plist: dict = {}
        eligibility_files = None
        ai_file = None
        basic_plists: dict = {}
        basic_plists_ownership: dict = {}
        files_data: dict = {}
        uses_domains: bool = False
        # K3: enabled MobileGestalt tweaks found on the Tweaks / Eligibility
        # pages (SpoofModel, AIGestalt, DynamicIsland, ...). They cannot be
        # written as plain plists — they patch the device's MobileGestalt
        # plist, which is loaded and validated after the loop.
        gestalt_tweaks: list = []
        # create the restore file list
        files_to_restore: list[FileToRestore] = [
        ]
        tmp_dirs = [] # temporary directory for unzipping pb and template files

        hotload = HotLoad(self.pref_manager.settings)
        hotload_version = self.get_current_device_version()
        hotload_model = self.get_current_device_model()
        hotload_skipped = []
        # stale/blocked tweaks are skipped; whole hidden features are never applied
        hotload_hidden_names = hotload.hidden_tweak_names(
            device_version=hotload_version, device_model=hotload_model)

        # Wave 10 backend gate: one shared MobileGestalt decision for the
        # whole pass. Locked/unknown clears any stale ON state before files
        # are generated, and the per-tweak pre-loop below skips anything
        # undeliverable (removed tombstones, registry version/device-class
        # locks, MobileGestalt capability) with a logged reason instead of
        # letting the UI/backend disagree.
        device_build = self.get_current_device_build()
        gestalt_decision = mobilegestalt_decision(device_build, hotload_version)
        if not gestalt_decision.supported:
            cleared = clear_unsupported_mobilegestalt_state(gestalt_decision)
            if cleared:
                log_warn("Cleared unsupported MobileGestalt tweak state before apply: "
                         + ", ".join(sorted(cleared)))
        # Wave 10 Package 1: audit research-only rows are contained on the
        # audited target. Clear stale ON state before generation so it can
        # neither produce a payload nor be counted as a ship feature; the
        # per-tweak deliverability gate below remains as defense in depth.
        cleared_research = clear_audit_research_only_state(
            hotload_version, device_build)
        if cleared_research:
            log_warn("Cleared audit research-only tweak state before apply: "
                     + ", ".join(sorted(cleared_research)))
        is_iphone_device = hotload_model.startswith("iPhone") if hotload_model else True
        backend_skipped: list[dict] = []

        # Wave 10 Apply Journal snapshot: one entry per tweak enabled at
        # snapshot time (after HotLoad daemon forcing, before the state
        # clears below so cleared tweaks still get their skipped entry).
        journal = getattr(self, "_current_journal", None)
        j_side = {"slices": {}, "plist": {}, "bookrestore": set()}
        j_entries: dict = {}
        j_current = None
        if journal is not None:
            try:
                for _jname, _jtweak in tweaks.items():
                    if not getattr(_jtweak, "enabled", False):
                        continue
                    if _jname in (TweakID.PosterBoard, TweakID.Templates):
                        try:
                            if _jtweak.is_empty():
                                continue
                        except Exception:
                            pass
                    _jkey = _jname.name if hasattr(_jname, "name") else str(_jname)
                    j_entries[_jkey] = self._journal_describe(
                        journal, _jname, _jtweak)
            except Exception as e:
                log_warn(f"Apply Journal snapshot failed: {e}")
                journal = None

        if journal is not None:
            # Tweaks force-cleared above (MobileGestalt lock / audit
            # research-only containment) are disabled by snapshot time;
            # they still earn a skipped entry with the gate's reason.
            for _cname in list(cleared or []) + list(cleared_research or []):
                if _cname in j_entries:
                    continue
                for _tid, _tw in tweaks.items():
                    if (_tid.name if hasattr(_tid, "name") else str(_tid)) == _cname:
                        j_entries[_cname] = self._journal_describe(
                            journal, _tid, _tw)
                        break

        def j_skip(tname, reason, *, hotload_reason=None, compat_reason=None):
            if journal is None:
                return
            key = tname.name if hasattr(tname, "name") else str(tname)
            for entry in j_entries.get(key, []):
                if entry["status"] != "requested":
                    continue
                entry["status"] = TW_SKIPPED
                entry["skip_reason"] = reason
                if hotload_reason is not None:
                    entry["hotload"] = {"result": "skipped",
                                        "reason": hotload_reason}
                if compat_reason is not None:
                    entry["compatibility"] = {"result": "incompatible",
                                              "reason": compat_reason}

        def j_fail(tname, err):
            if journal is None or tname is None:
                return
            key = tname.name if hasattr(tname, "name") else str(tname)
            for entry in j_entries.get(key, []):
                if entry["status"] == "requested":
                    entry["status"] = TW_FAILED
                    entry["error"] = f"{type(err).__name__}: {err}"

        if journal is not None:
            for _cname in (cleared or []):
                j_skip(_cname, "mobilegestalt_unsupported_build")
            for _cname in (cleared_research or []):
                j_skip(_cname, "AUDIT_RESEARCH_ONLY")

        try:
            # set the plist keys
            for tweak_name in tweaks:
                tweak = tweaks[tweak_name]
                # Backend pre-loop gate (Wave 10): an enabled tweak that is
                # removed, version/device-class locked, or MobileGestalt-
                # backed on a locked/unknown device is skipped before any
                # file is generated. The reason is logged with its stable
                # reason_code; skipped tweaks contribute no payload and so
                # never enter the sparse signature / lastapply record.
                if getattr(tweak, "enabled", False):
                    deliverable, reason_code, reason = tweak_deliverability(
                        tweak_name, device_version=hotload_version,
                        device_build=device_build,
                        is_iphone=is_iphone_device, tweak=tweak)
                    if not deliverable:
                        backend_skipped.append({
                            "tweak_id": tweak_name.name
                            if hasattr(tweak_name, "name") else str(tweak_name),
                            "reason_code": reason_code,
                            "reason": reason,
                        })
                        if requires_gestalt(tweak_name, tweak):
                            j_skip(tweak_name, "mobilegestalt_unsupported_build")
                        elif reason_code in ("VERSION_BELOW_MIN",
                                             "VERSION_ABOVE_MAX",
                                             "IPHONE_ONLY", "IPAD_ONLY"):
                            j_skip(tweak_name, "registry_incompatible",
                                   compat_reason=reason)
                        else:
                            j_skip(tweak_name, reason_code)
                        log_warn(f"Skipping tweak {backend_skipped[-1]['tweak_id']}: "
                                 f"{reason_code} — {reason}")
                        continue
                    # Hard delivery-model guard: a plain plist tweak must
                    # never write the MobileGestalt cache file directly.
                    # MobileGestalt content only ever rides the validated
                    # CacheExtra merge below (FileLocation.mga there).
                    if (isinstance(tweak, BasicPlistTweak)
                            and getattr(tweak, "file_location", None) == FileLocation.mga):
                        backend_skipped.append({
                            "tweak_id": tweak_name.name
                            if hasattr(tweak_name, "name") else str(tweak_name),
                            "reason_code": "WRONG_DELIVERY_MODEL",
                            "reason": "BasicPlistTweak may not write FileLocation.mga.",
                        })
                        j_skip(tweak_name, "WRONG_DELIVERY_MODEL")
                        log_warn(f"Skipping tweak {backend_skipped[-1]['tweak_id']}: "
                                 "WRONG_DELIVERY_MODEL — BasicPlistTweak may not "
                                 "write FileLocation.mga.")
                        continue
                    # Risky CustomResolution backend gate (Wave 10 P0): the
                    # GUI only checks that the fields parse as ints. The
                    # backend is authoritative — canvas keys only, integer
                    # dimensions inside the existing RDAR canvas envelope,
                    # otherwise the tweak is skipped before any payload is
                    # generated. Passing this gate is a safety check, not a
                    # claim the resolution works on this device.
                    if tweak_name == TweakID.CustomResolution:
                        res_ok, res_code, res_reason = validate_custom_resolution(
                            getattr(tweak, "value", None))
                        if not res_ok:
                            backend_skipped.append({
                                "tweak_id": tweak_name.name
                                if hasattr(tweak_name, "name") else str(tweak_name),
                                "reason_code": res_code,
                                "reason": res_reason,
                            })
                            j_skip(tweak_name, res_code)
                            log_warn(f"Skipping tweak {backend_skipped[-1]['tweak_id']}: "
                                     f"{res_code} — {res_reason}")
                            continue
                # Data-driven research-only families (PosterBoard /
                # Templates) select work by queued files rather than the
                # enabled flag, so the enabled-only gate above is not enough
                # for them. On the audited target they are skipped before
                # any payload is generated; queued user data is left intact.
                if (tweak_name in (TweakID.PosterBoard, TweakID.Templates)
                        and is_audit_research_only(tweak_name)
                        and is_audit_target(hotload_version, device_build)
                        and not tweak.is_empty()):
                    backend_skipped.append({
                        "tweak_id": tweak_name.name
                        if hasattr(tweak_name, "name") else str(tweak_name),
                        "reason_code": "AUDIT_RESEARCH_ONLY",
                        "reason": "Research-only in the Wave 10 audit; not a "
                                  "supported iOS 26.6.1 ship feature.",
                    })
                    j_skip(tweak_name, "AUDIT_RESEARCH_ONLY")
                    log_warn(f"Skipping tweak {backend_skipped[-1]['tweak_id']}: "
                             "AUDIT_RESEARCH_ONLY — Research-only in the Wave 10 "
                             "audit; not a supported iOS 26.6.1 ship feature.")
                    continue
                # HotLoad: never apply tweaks flagged as dangerous/broken for
                # this device / iOS version (kill switch off -> no rules match),
                # and never apply tweaks of a hidden feature.
                # B13 FIX: hotload_hidden_names holds TweakID *names* (strings),
                # while tweak_name here is a TweakID enum member — comparing
                # them directly was always False, so hidden features were
                # never skipped. Compare .name instead. (rule_for() already
                # did this correctly via getattr(tweak_id, "name", ...).)
                if (tweak_name.name in hotload_hidden_names
                        or hotload.rule_for(tweak_name,
                                            device_version=hotload_version,
                                            device_model=hotload_model) is not None):
                    hotload_skipped.append(tweak_name)
                    if getattr(tweak, "enabled", False):
                        j_skip(tweak_name,
                               "hotload_hidden_feature"
                               if tweak_name.name in hotload_hidden_names
                               else "hotload_rule",
                               hotload_reason="HotLoad safety rules flagged "
                                              "this tweak for this device.")
                    continue
                j_current = tweak_name
                j_start = len(files_to_restore)
                j_plist_before = {loc: dict(d) for loc, d in basic_plists.items()}
                j_flag_before = {c: (dict(v) if isinstance(v, dict) else v)
                                 for c, v in flag_plist.items()}
                if isinstance(tweak, FeatureFlagTweak):
                    # ported from leminlimez/Nugget: collect every enabled
                    # feature flag into one plist, written to
                    # /var/preferences/FeatureFlags/Global.plist below
                    flag_plist = tweak.apply_tweak(flag_plist)
                elif isinstance(tweak, BasicPlistTweak) or isinstance(tweak, AdvancedPlistTweak):
                    basic_plists = tweak.apply_tweak(basic_plists)
                    basic_plists_ownership[tweak.file_location] = tweak.owner
                elif isinstance(tweak, NullifyFileTweak):
                    tweak.apply_tweak(files_data)
                    if tweak.enabled and tweak.file_location.value.startswith("/var/mobile/"):
                        uses_domains = True
                elif isinstance(tweak, PosterboardTweak) or isinstance(tweak, TemplatesTweak):
                    tmp_dirs.append(TemporaryDirectory())
                    tweak.apply_tweak(
                        files_to_restore=files_to_restore,
                        output_dir=fix_windows_path(tmp_dirs[len(tmp_dirs)-1].name),
                        templates=templates,
                        version=self.get_current_device_version(),
                        force_pb_refresh=self.pref_manager.auto_refresh_posterboard,
                        update_label=update_label
                    )
                    if tweak.uses_domains():
                        uses_domains = True
                elif isinstance(tweak, IconThemesTweak):
                    tweak.apply_tweak(
                        files_to_restore=files_to_restore,
                        update_label=update_label
                    )
                    if tweak.uses_domains():
                        uses_domains = True
                elif isinstance(tweak, EligibilityTweak):
                    # Ported from leminlimez/Nugget: EU Enabler files.
                    # Nugget delivers these via BookRestore; this fork has no
                    # BookRestore, so files that map to a backup domain go
                    # through the sparse-restore list below, while the
                    # /var/MobileAsset/... Config.plist (not a backup domain)
                    # is skipped with a warning (see post-loop handling).
                    eligibility_files = tweak.apply_tweak()
                elif isinstance(tweak, AITweak):
                    # Ported from leminlimez/Nugget: Apple Intelligence
                    # eligibility file (/var/db/eligibilityd/eligibility.plist,
                    # DatabaseDomain -> sparse-restorable).
                    ai_file = tweak.apply_tweak()
                elif isinstance(tweak, BookRestoreFileTweak):
                    # Ported from leminlimez/Nugget (there: skipped in the
                    # sparse loop, delivered via BookRestore). This fork has
                    # no BookRestore; both placeholder paths live in backup
                    # domains, so they go straight into the restore list.
                    br_files = tweak.apply_tweak()
                    if br_files:
                        files_to_restore.extend(br_files)
                elif isinstance(tweak, StatusBarTweak):
                    if Version(self.get_current_device_version()) >= Version("27.0"):
                        # iOS 27: the classic binary statusBarOverrides file is
                        # dead and the Speakeasy feature flag cannot be written,
                        # but SpringBoard unarchives the carrier name itself
                        # from StatusBarOverrides.archive in HomeDomain.
                        tweak.apply_ios27_tweak(files_to_restore)
                        if tweak.enabled:
                            uses_domains = True
                            # Defense in depth (Wave 10): the classic-binary
                            # no-SIM feature never delivers on iOS 27.
                            if journal is not None:
                                for entry in j_entries.get("StatusBar", []):
                                    if (entry.get("id") == "statusbar.full_signal_bars_no_sim"
                                            and entry["status"] == "requested"):
                                        entry["status"] = TW_SKIPPED
                                        entry["skip_reason"] = "statusbar_unsupported_ios"
                    else:
                        # iOS 26 and below: classic binary statusBarOverrides
                        # in HomeDomain.
                        tweak.apply_classic_tweak(files_to_restore)
                        if tweak.enabled:
                            uses_domains = True
                elif isinstance(tweak, (MobileGestaltTweak, MobileGestaltPickerTweak,
                                        MobileGestaltMultiTweak, MobileGestaltCacheDataTweak)):
                    # K3: these were silently skipped by the old chain, so
                    # switches like SpoofModel / AIGestalt on the Tweaks and
                    # Eligibility pages did nothing on Apply. Collect the
                    # enabled ones; they are merged into the device's
                    # MobileGestalt plist after the loop (needs the user's
                    # base plist file, like the MobileGestalt page flow).
                    if tweak.enabled:
                        gestalt_tweaks.append(tweak)
                # Wave 10 Apply Journal: record what this tweak generated
                # (file slice + merged-plist contributions) for the attach
                # step. Entries stay "requested" until files are attached.
                if journal is not None:
                    _jkey = (tweak_name.name if hasattr(tweak_name, "name")
                             else str(tweak_name))
                    _jentries = j_entries.get(_jkey, [])
                    if _jentries and len(files_to_restore) > j_start:
                        for _entry in _jentries:
                            j_side["slices"].setdefault(id(_entry), []).append(
                                (j_start, len(files_to_restore)))
                    if _jentries and getattr(tweak, "enabled", False):
                        if isinstance(tweak, (BasicPlistTweak, AdvancedPlistTweak)):
                            _loc = tweak.file_location
                            _after = basic_plists.get(_loc, {})
                            _before = j_plist_before.get(_loc, {})
                            _keys = [k for k, v in _after.items()
                                     if k not in _before or _before[k] != v]
                            if _keys:
                                for _entry in _jentries:
                                    j_side["plist"][id(_entry)] = (_loc, _keys)
                        elif isinstance(tweak, FeatureFlagTweak):
                            _after = flag_plist
                            _before = j_flag_before
                            _keys = [k for k, v in _after.items()
                                     if k not in _before or _before[k] != v]
                            if _keys:
                                for _entry in _jentries:
                                    j_side["plist"][id(_entry)] = (
                                        FileLocation.featureflags, _keys)
                        elif isinstance(tweak, NullifyFileTweak):
                            for _entry in _jentries:
                                j_side["plist"][id(_entry)] = (
                                    tweak.file_location, [])

            if hotload_skipped:
                names = sorted(t.name if hasattr(t, "name") else str(t) for t in hotload_skipped)
                update_label(QCoreApplication.tr(
                    "Skipped HotLoad-flagged tweaks: ") + ", ".join(names))

            if backend_skipped:
                summary = ", ".join(
                    f"{entry['tweak_id']} ({entry['reason_code']})"
                    for entry in backend_skipped)
                update_label(QCoreApplication.tr(
                    "Skipped unsupported/removed tweaks: ") + summary)

            # Eligibility / Apple Intelligence files (ported from Nugget).
            # /var/db/... paths are DatabaseDomain and go through the normal
            # sparse-restore list. /var/MobileAsset/... is NOT a backup domain:
            # Nugget delivers it via BookRestore, which this fork does not
            # have, so it is skipped here with an explicit warning instead of
            # silently producing a broken restore entry.
            if eligibility_files:
                for elig_file in eligibility_files:
                    _rel_path, domain = self.get_domain_for_path(elig_file.restore_path)
                    if domain:
                        self.concat_file(
                            contents=elig_file.contents,
                            path=elig_file.restore_path,
                            files_to_restore=files_to_restore,
                        )
                    else:
                        update_label(QCoreApplication.tr(
                            "Skipped (needs BookRestore, not supported by this fork): ")
                            + elig_file.restore_path)
                        j_side["bookrestore"].add(TweakID.EUEnabler.name)
            if ai_file is not None:
                self.concat_file(
                    contents=ai_file.contents,
                    path=ai_file.restore_path,
                    files_to_restore=files_to_restore,
                )

            # K3: MobileGestalt tweaks enabled on the Tweaks / Eligibility /
            # MobileGestalt pages (SpoofModel, AIGestalt, DynamicIsland, ...).
            # They patch the device's own MobileGestalt plist (CacheExtra /
            # CacheData), so the user's base plist file is required — the
            # same file the MobileGestalt page uses. Without it this raises
            # a clear error instead of silently applying nothing.
            if gestalt_tweaks:
                if not gestalt_decision.supported:
                    # B14 FIX: never poison the whole apply. Locked gestalt
                    # builds used to raise here, failing EVERYTHING (including
                    # unrelated tweaks). Skip the gestalt tweaks with a clear
                    # warning and apply the rest. Enabled gestalt tweaks were
                    # already skipped per-tweak in the pre-loop.
                    log_warn("MobileGestalt tweaks skipped: "
                             f"{gestalt_decision.reason_code} — "
                             f"{gestalt_decision.user_message}")
                    if journal is not None:
                        for _gname, _gtweak in tweaks.items():
                            if any(_gtweak is _g for _g in gestalt_tweaks):
                                j_skip(_gname, "mobilegestalt_unsupported_build")
                    update_label(QCoreApplication.tr(
                        "Note: MobileGestalt tweaks were skipped (not supported on this iOS version)."))
                else:
                    gestalt_plist = self._load_gestalt_plist(update_label)
                    for gtweak in gestalt_tweaks:
                        gestalt_plist = gtweak.apply_tweak(gestalt_plist)
                    self.concat_file(
                        contents=plistlib.dumps(gestalt_plist),
                        path=FileLocation.mga.value,
                        files_to_restore=files_to_restore,
                        owner=501, group=501,
                    )
                    if journal is not None:
                        _mga_idx = len(files_to_restore) - 1
                        for _gname, _gtweak in tweaks.items():
                            if any(_gtweak is _g for _g in gestalt_tweaks):
                                _gkey = (_gname.name if hasattr(_gname, "name")
                                         else str(_gname))
                                for _entry in j_entries.get(_gkey, []):
                                    j_side["slices"].setdefault(
                                        id(_entry), []).append(
                                        (_mga_idx, _mga_idx + 1))
            if len(CustomGestaltTweaks.custom_tweaks) > 0:
                # Wave 10 Package 1: killed product surface. A stale
                # in-memory custom-key list never triggers the MobileGestalt
                # merge and never contributes CacheExtra payload.
                log_warn("CustomGestaltTweaks ignored: killed Wave 10 product "
                         "surface; no custom CacheExtra payload was generated.")

            # Generate backup
            update_label(QCoreApplication.tr("Generating backup..."))
            if len(flag_plist) > 0:
                self.concat_file(
                    contents=plistlib.dumps(flag_plist),
                    path=FileLocation.featureflags.value,
                    files_to_restore=files_to_restore
                )
            
            await self.add_skip_setup(files_to_restore, uses_domains)
            for location, plist in basic_plists.items():
                if location in basic_plists_ownership:
                    ownership = basic_plists_ownership[location]
                else:
                    ownership = 501
                self.concat_file(
                    contents=plistlib.dumps(plist),
                    path=location.value,
                    files_to_restore=files_to_restore,
                    owner=ownership, group=ownership
                )
            # iOS 27+: also write .GlobalPreferences.plist to HomeDomain so
            # tweaks that depend on it survive the Phase 3 protective backup
            # restore. ManagedPreferencesDomain is the primary location;
            # HomeDomain is a secondary copy for iOS 27 compatibility.
            # (Phase 0 skips this file in the protective backup so Phase 3
            # cannot overwrite the tweak copy with a stale original.)
            #
            # SAFETY (B1, was K2): this write REPLACES the live file on the
            # device, so it must be a MERGE of the user's live settings with
            # the tweak keys — never a tweak-only dict (that wiped the user's
            # keyboard/locale/region). The merge base is the live plist
            # extracted from the Phase 0 master backup (_register_gp_base).
            # Without a base (raw sparse / skipped backup / encrypted
            # manifest) the HomeDomain copy is SKIPPED with a warning: the
            # Managed Preferences overlay (primary location) still applies.
            # iOS 26 keeps the upstream Nugget behavior: overlay only.
            gp_tweaks = basic_plists.get(FileLocation.globalPreferences)
            if (gp_tweaks
                    and Version(self.get_current_device_version()) >= Version("27.0")):
                gp_base = getattr(self, "_gp_base_plist", None)
                if isinstance(gp_base, dict):
                    merged_gp = dict(gp_base)
                    merged_gp.update(gp_tweaks)
                    self.concat_file(
                        contents=plistlib.dumps(merged_gp),
                        path=FileLocation.globalPreferencesHomeDomain.value,
                        files_to_restore=files_to_restore,
                        owner=501, group=501
                    )
                    log_info(f"HomeDomain .GlobalPreferences.plist: merged {len(gp_tweaks)} "
                             f"tweak keys over {len(gp_base)} live keys")
                else:
                    log_warn("Skipping the iOS 27 HomeDomain .GlobalPreferences.plist write: "
                             "no live-settings merge base (protective backup did not capture it). "
                             "Your language/region/keyboard settings are left untouched; "
                             "GP tweaks still apply via the Managed Preferences overlay.")

            for location, data in files_data.items():
                self.concat_file(
                    contents=data,
                    path=location.value,
                    files_to_restore=files_to_restore,
                    owner=501, group=501
                )

            # Wave 10 Apply Journal: staging is complete — attach the file
            # records, resolve per-tweak staged/skipped/failed states, and
            # persist the post-staging state before the restore begins.
            if journal is not None:
                journal.attach_files(files_to_restore)
                self._journal_attach(journal, j_side)
                try:
                    journal.write()
                except Exception as e:
                    log_warn(f"Apply Journal staging write failed: {e}")

            # Check if backup encryption is enabled and handle it
            backup_password = ""
            if Version(self.get_current_device_version()) >= Version("27.0"):
                # Phase 0's protective backup already established the
                # encryption state (and may have captured a password). Reusing
                # it avoids a whole extra lockdown session on every apply; only
                # when Phase 0 did not run (raw sparse / nothing to prepare)
                # do we pay for a real check here.
                known = self._known_backup_encryption
                if known is None:
                    async with lockdown_session(self.get_current_device_udid()) as check_ld:
                        try:
                            async with Mobilebackup2Service(check_ld) as mb:
                                is_encrypted = await mb.get_will_encrypt()
                        except Exception as e:
                            if isinstance(e, NuggetException):
                                raise
                            log_warn(f"Failed to check backup encryption status: {e}")
                            is_encrypted = False
                else:
                    is_encrypted = known
                if is_encrypted:
                    if self.pref_manager.use_encrypted_backup:
                        # reuse the password entered for the cached backup, if any
                        backup_password = self._get_backup_password()
                        if backup_password:
                            log_info("Using existing backup encryption with provided password")
                            update_label(QCoreApplication.tr("Password accepted. Proceeding with encrypted restore..."))
                        else:
                            # User wants to keep encryption - ask for password to use it
                            update_label(QCoreApplication.tr("Backup encryption is enabled. We'll use it for the restore."))
                            update_label(QCoreApplication.tr("Please enter your iTunes/Finder backup password:"))
                            if prompt_password is None:
                                raise NuggetException(QCoreApplication.tr("Backup password is required for encrypted restore. Please provide the password or disable encryption in iTunes/Finder."))
                            password = prompt_password(
                                QCoreApplication.tr("Backup Encryption Password"),
                                QCoreApplication.tr("Enter your iTunes/Finder backup password (required for encrypted restore):"))
                            if password:
                                backup_password = password
                                log_info("Using existing backup encryption with provided password")
                                update_label(QCoreApplication.tr("Password accepted. Proceeding with encrypted restore..."))
                            else:
                                raise NuggetException(QCoreApplication.tr("Backup password is required for encrypted restore. Please provide the password or disable encryption in iTunes/Finder."))
                    else:
                        # User doesn't want encryption - show friendly error
                        raise NuggetException(QCoreApplication.tr(
                            "Backup encryption is enabled on your iPhone.\n\n"
                            "GoldenNugget needs to temporarily disable it to apply tweaks safely.\n\n"
                            "Please choose one:\n"
                            "1. Disable encryption on your iPhone: Settings → General → Transfer or Reset iPhone → Backup Password → Turn Off\n"
                            "2. Or enable \"Use Encrypted Backups (Experimental)\" in GoldenNugget Settings → enter your backup password when prompted.\n\n"
                            "Tip: Option 1 is simpler if you don't know your backup password."
                        ))

            # restore to the device
            # include_keychain only when backup encryption is active — iOS rejects
            # keychain entries in an unencrypted backup, and the keychain is what
            # preserves Apple Watch pairing / iMessage identity across the wipe.
            try:
                final_alert = await self.start_restore(
                    files_to_restore, update_label, backup_password=backup_password,
                    prepared_backup_root=prepared_backup_root,
                    skip_protective_backup=skip_protective_backup,
                    include_keychain=bool(backup_password),
                    prompt_choice=prompt_choice,
                    supervised=self.pref_manager.supervised,
                    organization_name=self.pref_manager.organization_name)
            except Exception as restore_err:
                # The restore call raised: staged tweaks were not delivered.
                if journal is not None and not journal.finalized:
                    for _entry in journal.data["tweaks"]:
                        if _entry["status"] == TW_STAGED:
                            _entry["status"] = TW_NOT_DELIVERED
                    self._finish_journal(
                        journal, "failed",
                        error=f"{type(restore_err).__name__}: {restore_err}")
                raise
            if journal is not None and not journal.finalized:
                for _entry in journal.data["tweaks"]:
                    if _entry["status"] == TW_STAGED:
                        _entry["status"] = TW_DELIVERED
                _partial = any(
                    _entry["status"] in (TW_FAILED, TW_NOT_DELIVERED)
                    for _entry in journal.data["tweaks"])
                self._finish_journal(
                    journal, "partial" if _partial else "success")
            return final_alert, files_to_restore
        except Exception as pass_err:
            # Generation (or an unexpected mid-pass failure): the entry for
            # the tweak being generated is marked failed; the operation ends
            # failed. Restore failures already finalized above.
            if journal is not None and not journal.finalized:
                j_fail(j_current, pass_err)
                for _entry in journal.data["tweaks"]:
                    if _entry["status"] == TW_STAGED:
                        _entry["status"] = TW_NOT_DELIVERED
                self._finish_journal(
                    journal, "failed",
                    error=f"{type(pass_err).__name__}: {pass_err}")
            raise
        finally:
            if len(tmp_dirs) > 0:
                for tmp_dir in tmp_dirs:
                    try:
                        tmp_dir.cleanup()
                    except Exception as e:
                        # ignore clean up errors
                        print(str(e))

    ## RESETTING TWEAKS
    def reset_tweaks(self, reset_pages: list[Page], settings: QSettings, update_label=lambda x: None, show_alert=lambda x: None, prompt_choice=None):
        asyncio.run(self._reset_tweaks(reset_pages, settings, update_label, show_alert, prompt_choice))
    async def _reset_tweaks(self, reset_pages: list[Page], settings: QSettings, update_label=lambda x: None, show_alert=lambda x: None, prompt_choice=None):
        journal = None
        j_page_paths: dict = {}
        final_alert = None
        files_to_restore: list = []
        try:
            self._raise_if_unsupported()
            # Wave 10 Apply Journal: one entry per requested reset page.
            self.last_apply_journal_path = None
            self._journal_error = None
            try:
                journal = begin_journal("reset", device=self._journal_device_info())
            except Exception as e:
                # The journal is auxiliary logging; it must never block a reset.
                log_warn(f"Apply Journal reset init failed: {e}")
                journal = None
            self._current_journal = journal
            if journal is not None:
                for _page in reset_pages:
                    journal.add_entry({
                        "id": f"reset.{_page.name.lower()}",
                        "tweak_id": None,
                        "name": _page.getPageName(),
                        "family": "Reset",
                        "kind": "reset_page",
                        "requested": True,
                        "source": "reset_page",
                        "operation": {"page": _page.name},
                    })
            # create the restore file list
            udid = self.get_current_device_udid()
            if not udid:
                raise NuggetException(QCoreApplication.tr("No device connected."))
            dev_version = self.get_current_device_version()
            # No original-plist capture: reset writes stock values straight to
            # the device on every iOS version. Pulling the device's own plists
            # first (the old psysbackup step) was only ever done for iOS 27, and
            # it did not buy much — the managed-preferences copy the tweaks write
            # to already holds the tweaked values, so restoring a captured
            # "original" re-wrote the very tweaks the user asked to remove.
            files_to_null: list[str] = []
            uses_domains = False
            _page_starts: list = []
            _null_starts: list = []

            # plain if-chains, not match: the page set is a long, stable list
            # and a flat chain keeps the diff readable when pages are added
            for page in reset_pages:
                _page_starts.append(len(files_to_restore))
                _null_starts.append(len(files_to_null))
                if page == Page.StatusBar:
                    ## STATUS BAR
                    dev_version = self.get_current_device_version()
                    if dev_version and Version(dev_version) >= Version("27.0"):
                        # iOS 27: SpringBoard reads the carrier name from
                        # StatusBarOverrides.archive. Writing a valid archive
                        # with no cellular entries is the reset -- SpringBoard
                        # decodes it as "no overrides" and unlinks the file
                        # itself, which brings the stock carrier names back.
                        # The old SpeakeasyNewStatusBar FeatureFlags write is
                        # gone: a restore cannot write that plist on iOS 27
                        # anyway, and poking /var/preferences risks tripping
                        # Security Recovery.
                        self.concat_file(
                            contents=build_reset_archive(),
                            path=FileLocation.statusBarOverridesArchive.value,
                            files_to_restore=files_to_restore
                        )
                        uses_domains = True
                    else:
                        # iOS 26 and below: the tweak writes a classic binary
                        # statusBarOverrides file. Reset it to a fresh (all-
                        # default) override struct so the status bar returns to
                        # stock — the apply path reads the same file, so an
                        # untouched zeroed file makes every override "off".
                        fresh = StatusBarTweak()
                        files_to_restore.append(FileToRestore(
                            contents=fresh.setter.get_data(),
                            restore_path="/Library/SpringBoard/statusBarOverrides",
                            domain="HomeDomain"
                        ))
                elif page == Page.Springboard:
                    ## SPRINGBOARD
                    files_to_null.append(FileLocation.springboard.value)
                    files_to_null.append(FileLocation.uikit.value)
                    # B21 FIX: reset used to skip these three SpringBoard-
                    # family files, leaving their tweaks (footnote text,
                    # AirDrop override, watchOS compat) permanently applied.
                    files_to_null.append(FileLocation.footnote.value)
                    files_to_null.append(FileLocation.airdrop.value)
                    files_to_null.append(FileLocation.nanoregistry.value)
                elif page == Page.Daemons:
                    ## DAEMONS
                    # REAUDIT FIX: was a forked copy of the B22 defaults dict
                    # in tweak_loader.load_daemons() — now uses the single
                    # source of truth so apply and reset can never drift.
                    from src.tweaks.daemons_tweak import UPSTREAM_DEFAULT_DAEMONS
                    self.concat_file(
                        contents=plistlib.dumps(dict(UPSTREAM_DEFAULT_DAEMONS)),
                        path=FileLocation.disabledDaemons.value,
                        files_to_restore=files_to_restore,
                        owner=0, group=0
                    )
                    uses_domains = True
                elif page == Page.InternalOptions:
                    ## INTERNAL OPTIONS
                    files_to_null.append(FileLocation.globalPreferences.value)
                    # B16 FIX: the HomeDomain copy is only ever written on
                    # iOS 27+ (see the B1 merge in _apply_tweak_pass). Nulling
                    # it on iOS 26 made reset MORE destructive than apply —
                    # wiping a live user file the apply never touched.
                    dev_version = self.get_current_device_version()
                    if dev_version and Version(dev_version) >= Version("27.0"):
                        # B10 FIX: on iOS 27 the HomeDomain copy holds the
                        # MERGED plist (user base + tweak keys). Nulling it
                        # would wipe the user's language/region/keyboard, so
                        # reset restores the pristine base captured at apply
                        # time instead. No base on record -> skip the file
                        # entirely rather than destroy user data.
                        from src.restore.lastapply import load_gp_base
                        _gp_base = load_gp_base(udid)
                        if _gp_base is not None:
                            self.concat_file(
                                contents=plistlib.dumps(_gp_base),
                                path=FileLocation.globalPreferencesHomeDomain.value,
                                files_to_restore=files_to_restore
                            )
                            uses_domains = True
                        else:
                            log_warn("iOS 27 HomeDomain .GlobalPreferences.plist reset skipped: "
                                     "no pristine base on record — leaving the file untouched "
                                     "rather than wiping user preferences.")
                    files_to_null.append(FileLocation.appStore.value)
                    files_to_null.append(FileLocation.backboardd.value)
                    files_to_null.append(FileLocation.coreMotion.value)
                    files_to_null.append(FileLocation.pasteboard.value)
                    files_to_null.append(FileLocation.notes.value)
                elif page == Page.Tweaks:
                    ## FEATURE FLAGS (B10 FIX) — the only Tweaks-page family
                    ## without its own reset page. Stock = no overrides, i.e.
                    ## an empty Global.plist (nulling the file entirely is
                    ## riskier: the OS expects the plist to exist).
                    self.concat_file(
                        contents=plistlib.dumps({}),
                        path=FileLocation.featureflags.value,
                        files_to_restore=files_to_restore,
                        owner=501, group=501
                    )
                    uses_domains = True
                elif page == Page.LiquidGlass:
                    ## LIQUID GLASS (B10 FIX) — the 98 Solarium keys all target
                    ## .GlobalPreferences.plist, so resetting them = nulling
                    ## the GP files (same files the Internal Options reset
                    ## covers, but scoped to this page's checkbox).
                    files_to_null.append(FileLocation.globalPreferences.value)
                    # 2026-10-01: the "Tinted Glass (official iOS setting)"
                    # tweak writes UIViewGlassLegibilitySetting to the managed
                    # com.apple.UIKit.plist, so the Liquid Glass reset must
                    # clear that file too (it is otherwise only nulled by the
                    # SpringBoard page reset).
                    files_to_null.append(FileLocation.uikit.value)
                    # 2026-10-01: the per-app E0 experiments write
                    # FailSolariumHardwareCheck to per-bundle managed plists,
                    # so the Liquid Glass reset must clear those files too.
                    for _app_loc in (FileLocation.appMessages,
                                     FileLocation.appSafari,
                                     FileLocation.appSettings,
                                     FileLocation.appMail,
                                     FileLocation.appPhotos,
                                     FileLocation.appCamera,
                                     FileLocation.appPhone):
                        files_to_null.append(_app_loc.value)
                    dev_version = self.get_current_device_version()
                    if dev_version and Version(dev_version) >= Version("27.0"):
                        # Same B10 rule as InternalOptions above: the iOS 27
                        # HomeDomain copy is a merged user+tweak plist — restore
                        # the pristine base, never null it.
                        from src.restore.lastapply import load_gp_base
                        _gp_base_lg = load_gp_base(udid)
                        if _gp_base_lg is not None:
                            self.concat_file(
                                contents=plistlib.dumps(_gp_base_lg),
                                path=FileLocation.globalPreferencesHomeDomain.value,
                                files_to_restore=files_to_restore
                            )
                            uses_domains = True
                        else:
                            log_warn("iOS 27 HomeDomain .GlobalPreferences.plist reset skipped: "
                                     "no pristine base on record — leaving the file untouched.")
                elif page == Page.RiskyTweaks:
                    ## RISKY (B10 FIX) — DisableOTA + CustomResolution. Both
                    ## are full-file writes, so nulling returns them to stock.
                    files_to_null.append(FileLocation.ota.value)
                    files_to_null.append(FileLocation.resolution.value)
                elif page == Page.EUEnabler:
                    ## ELIGIBILITY (B10 FIX) — null the files EUEnabler /
                    ## Apple Intelligence eligibility actually deliver.
                    ## (/var/MobileAsset/... was never deliverable and is not
                    ## written, so there is nothing to reset for it.)
                    files_to_null.append("/var/db/os_eligibility/eligibility.plist")
                    files_to_null.append("/var/db/eligibilityd/eligibility.plist")
                elif page == Page.Gestalt:
                    ## MOBILE GESTALT (B10 FIX) — reset = write back the
                    ## PRISTINE device plist (the user-provided base file),
                    ## never null it: a missing MobileGestalt plist would
                    ## break the device.
                    try:
                        pristine = self._load_gestalt_plist(update_label)
                        self.concat_file(
                            contents=plistlib.dumps(pristine),
                            path=FileLocation.mga.value,
                            files_to_restore=files_to_restore,
                            owner=501, group=501,
                        )
                        uses_domains = True
                    except NuggetException as e:
                        log_warn(f"MobileGestalt reset skipped: {e}")

            _direct_total = len(files_to_restore)

            # Add the files to null from the list. Wave 10 P0: NEVER stage a
            # zero-byte plist on iOS 26.x (or any other version). A truncated
            # com.apple.springboard.plist can crash SpringBoard at boot on
            # iOS 26.2+, and a forced restore from there lands on iOS 27
            # because iOS 26.x is no longer signed. A valid empty plist is
            # the safe reset payload for every file in this list: it parses
            # and makes the system fall back to its default values. This
            # replaces the old iOS 26 zero-byte branch outright; there is no
            # version-dependent byte content anymore.
            reset_contents = plistlib.dumps({})
            for file_path in files_to_null:
                self.concat_file(
                    contents=reset_contents,
                    path=file_path,
                    files_to_restore=files_to_restore
                )

            await self.add_skip_setup(files_to_restore, uses_domains)

            # Wave 10 Apply Journal: attach the staged reset artifacts to
            # their page entries before the restore begins.
            if journal is not None:
                keys = journal.attach_files(files_to_restore)
                direct_end = _direct_total
                for _idx, _page in enumerate(reset_pages):
                    entry = journal.data["tweaks"][_idx]
                    start = _page_starts[_idx]
                    end = (_page_starts[_idx + 1]
                           if _idx + 1 < len(reset_pages) else direct_end)
                    page_keys = [keys[i] for i in range(start, end)]
                    null_end = (_null_starts[_idx + 1]
                                if _idx + 1 < len(reset_pages)
                                else len(files_to_null))
                    for _path in files_to_null[_null_starts[_idx]:null_end]:
                        _rel, _domain = self.get_domain_for_path(_path)
                        _key = f"{_domain}/{_rel.lstrip('/')}"
                        if _key in keys:
                            page_keys.append(_key)
                    # add_skip_setup files belong to no single page; they
                    # ride the last segment boundary and are left in the
                    # top-level file list only.
                    journal.associate(entry, page_keys)
                    entry["status"] = TW_STAGED if page_keys else TW_FAILED
                    if not page_keys:
                        entry["error"] = "no_file_staged"
                try:
                    journal.write()
                except Exception as e:
                    log_warn(f"Apply Journal reset staging write failed: {e}")

            # restore to the device
            final_alert = await self.start_restore(files_to_restore, update_label,
                                                   prompt_choice=prompt_choice)
            if journal is not None:
                for _entry in journal.data["tweaks"]:
                    if _entry["status"] == TW_STAGED:
                        _entry["status"] = TW_DELIVERED
                _partial = any(_entry["status"] == TW_FAILED
                               for _entry in journal.data["tweaks"])
                self._finish_journal(
                    journal, "partial" if _partial else "success")
            # the device is back to stock — drop the apply record so a future
            # apply never skips Phase 2 against a reset device. The pristine
            # GP base goes too: it described the pre-tweak device, which the
            # next apply will re-capture fresh from its own Phase 0 backup.
            from src.restore.lastapply import clear_lastapply, clear_gp_base
            udid = self.get_current_device_udid()
            if udid:
                clear_lastapply(udid)
                clear_gp_base(udid)
            update_label(QCoreApplication.tr("Success!"))
        except Exception as e:
            if journal is not None and not journal.finalized:
                for _entry in journal.data["tweaks"]:
                    if _entry["status"] == TW_STAGED:
                        _entry["status"] = TW_NOT_DELIVERED
                self._finish_journal(
                    journal, "failed", error=f"{type(e).__name__}: {e}")
            final_alert = show_apply_error(e, update_label, files_list=files_to_restore)
        finally:
            self._current_journal = None
            show_alert(final_alert)
