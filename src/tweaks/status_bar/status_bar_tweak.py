from .status_setter import Setter, StatusBarItem
from .statusbar_archive import ARCHIVE_DOMAIN, ARCHIVE_PATH, build_archive
from ..tweak_classes import Tweak, _notify_tweak_change
from src.utils.file_to_restore import FileToRestore

from cffi import FFI
ffi = FFI()

# --- Full Signal Bars (No SIM Visual) -------------------------------------
# Named v1 candidate recipe (Wave 10 buildspec §2.2): primary GSM bar count
# plus the signal-strength item (index 4) and cellular-service item (index 6)
# forced visible. The value 4 is provisional — it follows the only in-repo
# full-scale precedent (the iOS 27 archive cellular displayValue); whether
# the classic renderer wants 4 or 5 is decided by the device matrix, not by
# the generic GUI range. Research-only/unproven on iOS 26.6.1: this is a
# visual override candidate, never a claim of real cellular service.
FULL_SIGNAL_BARS = 4
FULL_SIGNAL_FILE = "HomeDomain/Library/SpringBoard/statusBarOverrides"
FULL_SIGNAL_FEATURE_ID = "statusbar.full_signal_bars_no_sim"
FULL_SIGNAL_FEATURE_NAME = "Full Signal Bars (No SIM Visual)"

# Display names for the raw dataNetworkType values, indexed exactly as
# Cowabunga Lite's NetworkTypes array and the vendored Nugget dropdown
# (src/qt/nugget741_ui.py pTypeDrp/sTypeDrp) write them: the GUI writes
# the raw index, the struct stores the raw index; only the label is new
# (fake-5G research 2026-10-09: 11="5G", 12="5G+", 13="5GUW",
# 14="5GUC"). Values outside the named range keep a neutral "Type N".
DATA_NETWORK_TYPE_LABELS = {
    0: "GPRS", 1: "EDGE", 2: "3G", 3: "4G", 4: "LTE", 5: "Wi-Fi",
    6: "Personal Hotspot", 7: "1x", 8: "5Gᴇ", 9: "LTE-A", 10: "LTE+",
    11: "5G", 12: "5G+", 13: "5GUW", 14: "5GUC",
}

def data_network_type_label(value: int) -> str:
    """Human label for a raw dataNetworkType value ("Type N" if unnamed)."""
    return DATA_NETWORK_TYPE_LABELS.get(value, f"Type {value}")

def _truncate_utf8(text: str, max_bytes: int) -> bytes:
    """Encode *text* as UTF-8, cutting at a character boundary so the result
    is at most *max_bytes* bytes.

    Char-count slicing (``text[:N].encode()``) is not enough here: N characters
    can encode to up to 4*N bytes, which overflows the fixed ``char[N]`` arrays
    and made cffi raise ``IndexError`` (crash) on emoji/CJK input.
    """
    data = text.encode("utf-8")
    while len(data) > max_bytes:
        text = text[:-1]
        data = text.encode("utf-8")
    return data

class StatusBarTweak(Tweak):
    def __init__(self):
        super().__init__(key=None)
        self.setter = Setter()

    def _apply_changes(self, overrides) -> None:
        setter = self.setter
        setter.apply_changes(overrides)
        _notify_tweak_change()
        return None

    # iOS 27+: the classic binary statusBarOverrides file is no longer read and
    # the SpeakeasyNewStatusBar feature flag cannot be written by a restore, so
    # the carrier name is delivered as the StatusBarOverrides.archive that
    # SpringBoard unarchives itself. It lives in HomeDomain, the same domain
    # the classic path uses, so this is an ordinary restore file -- no exploit.
    def apply_ios27_tweak(self, files_to_restore: list) -> None:
        """Stage StatusBarOverrides.archive (iOS 27+).

        Only the carrier names survive on iOS 27; every other override in the
        struct has no representation in the archive and is dropped, so the page
        hides them (see src/gui/ios/statusbar.py).
        """
        if not self.enabled:
            return
        primary = self.get_carrier_override() if self.is_carrier_overridden() else None
        secondary = self.get_secondary_carrier_override() if self.is_secondary_carrier_overridden() else None
        # NOTE (audit B30): don't stage the archive when there is nothing to
        # override — build_archive(None, None) is the *reset* record, and
        # writing it on a master-ON/empty page would clobber carrier state
        # for no reason.
        if primary is None and secondary is None:
            return
        files_to_restore.append(FileToRestore(
            contents=build_archive(primary, secondary),
            restore_path=ARCHIVE_PATH,
            domain=ARCHIVE_DOMAIN
        ))

    # iOS 26.x (pre-27): classic binary statusBarOverrides in HomeDomain.
    def apply_classic_tweak(self, files_to_restore: list) -> None:
        """Stage the classic binary status bar override file (iOS 26.x)."""
        if not self.enabled:
            return
        files_to_restore.append(FileToRestore(
            contents=self.setter.get_data(),
            restore_path="/Library/SpringBoard/statusBarOverrides",
            domain="HomeDomain"
        ))

    # --- generic helpers over the StatusBarOverrideData struct ---

    def _overrides(self):
        return self.setter.get_overrides()

    def _is_flag_overridden(self, flag: str) -> bool:
        return getattr(self._overrides(), flag) == 1

    def _get_str(self, field: str) -> str:
        return ffi.string(getattr(self._overrides().values, field)).decode()

    def _get_int(self, field: str) -> int:
        return getattr(self._overrides().values, field)

    def _set_flag(self, flag: str, field: str = None, value=None, max_len: int = None) -> None:
        overrides = self._overrides()
        setattr(overrides, flag, 1)
        if field is not None:
            if isinstance(value, str):
                # NOTE: truncate by encoded bytes, not characters -- the
                # destination is a fixed char[max_len] array and multibyte
                # input would otherwise overflow it (IndexError).
                data = _truncate_utf8(value, max_len) if max_len is not None else value.encode()
            else:
                data = value
            setattr(overrides.values, field, data)
        self._apply_changes(overrides)

    def _unset_flag(self, flag: str) -> None:
        overrides = self._overrides()
        setattr(overrides, flag, 0)
        self._apply_changes(overrides)

    ### PRIMARY CARRIER
    # CELLULAR SERVICE
    def is_cellular_service_overridden(self) -> bool:
        return self.is_item_overridden(StatusBarItem.CellularServiceStatusBarItem)
    def get_cellular_service_override(self) -> bool:
        return self.get_item_override(StatusBarItem.CellularServiceStatusBarItem)
    def set_cellular_service(self, shown: bool) -> None:
        self.set_item_override(StatusBarItem.CellularServiceStatusBarItem, shown)
    def unset_cellular_service(self) -> None:
        self.unset_item_override(StatusBarItem.CellularServiceStatusBarItem)

    # SERVICE STRING
    def is_carrier_overridden(self) -> bool:
        return self._is_flag_overridden("overrideServiceString")
    def get_carrier_override(self) -> str:
        return self._get_str("serviceString")
    def set_carrier_override(self, text: str) -> None:
        overrides = self._overrides()
        truncated = _truncate_utf8(text, 100)
        overrides.values.serviceString = truncated
        overrides.values.serviceCrossfadeString = truncated
        self._set_flag("overrideServiceString")
    def unset_carrier_override(self) -> None:
        self._unset_flag("overrideServiceString")

    # SERVICE BADGE
    def is_primary_service_badge_overridden(self) -> bool:
        return self._is_flag_overridden("overridePrimaryServiceBadgeString")
    def get_primary_service_badge_override(self) -> str:
        return self._get_str("primaryServiceBadgeString")
    def set_primary_service_badge(self, text: str) -> None:
        self._set_flag("overridePrimaryServiceBadgeString", "primaryServiceBadgeString", text, max_len=100)
    def unset_primary_service_badge(self) -> None:
        self._unset_flag("overridePrimaryServiceBadgeString")

    # DATA NETWORK TYPE
    def is_data_network_type_overridden(self) -> bool:
        return self._is_flag_overridden("overrideDataNetworkType")
    def get_data_network_type_override(self) -> int:
        return self._get_int("dataNetworkType")
    def set_data_network_type(self, id: int) -> None:
        self._set_flag("overrideDataNetworkType", "dataNetworkType", id)
        # The type glyph is only drawn when the cellular data network
        # item itself is enabled in the override struct (item 9; this is
        # how Cowabunga Lite / Nugget write it). Without this, a type
        # chosen while the item is hidden would silently never render.
        self.set_item_override(
            StatusBarItem.CellularDataNetworkStatusBarItem, True)
    def unset_data_network_type(self) -> None:
        self._unset_flag("overrideDataNetworkType")

    # GSM SIGNAL BARS
    def is_gsm_signal_strength_bars_overridden(self) -> bool:
        return self._is_flag_overridden("overrideGSMSignalStrengthBars")
    def get_gsm_signal_strength_bars_override(self) -> int:
        return self._get_int("GSMSignalStrengthBars")
    def set_gsm_signal_strength_bars(self, id: int) -> None:
        # NOTE (audit B29): do NOT force the cellular signal icon visible here.
        # Visibility is the user's own choice via the disable-icon toggles
        # (set_item_override); stomping itemIsEnabled would override it.
        self._set_flag("overrideGSMSignalStrengthBars", "GSMSignalStrengthBars", id)
    def unset_gsm_signal_strength_bars(self) -> None:
        self._unset_flag("overrideGSMSignalStrengthBars")

    # FULL SIGNAL BARS (NO SIM VISUAL)
    # Dedicated recipe: bar count + item visibility combined. This is the
    # ONLY caller allowed to combine them; the generic setter above must
    # keep respecting the user's own item-visibility choices (audit B29).
    def set_full_signal_bars_no_sim(self) -> None:
        self.set_gsm_signal_strength_bars(FULL_SIGNAL_BARS)
        self.set_item_override(StatusBarItem.CellularSignalStrengthStatusBarItem, True)
        self.set_item_override(StatusBarItem.CellularServiceStatusBarItem, True)

    def unset_full_signal_bars_no_sim(self) -> None:
        # Clears only the owned override flags; values stay in the struct
        # (existing _unset_flag semantics: no flag = stock rendering) and
        # every unrelated override is untouched.
        self.unset_gsm_signal_strength_bars()
        self.unset_item_override(StatusBarItem.CellularSignalStrengthStatusBarItem)
        self.unset_item_override(StatusBarItem.CellularServiceStatusBarItem)

    def is_full_signal_bars_no_sim_enabled(self) -> bool:
        return (
            self.is_gsm_signal_strength_bars_overridden()
            and self.get_gsm_signal_strength_bars_override() == FULL_SIGNAL_BARS
            and self.is_item_overridden(StatusBarItem.CellularSignalStrengthStatusBarItem)
            and self.get_item_override(StatusBarItem.CellularSignalStrengthStatusBarItem)
            and self.is_item_overridden(StatusBarItem.CellularServiceStatusBarItem)
            and self.get_item_override(StatusBarItem.CellularServiceStatusBarItem)
        )

    def describe_full_signal_bars_no_sim(self) -> dict:
        return {
            "id": FULL_SIGNAL_FEATURE_ID,
            "name": FULL_SIGNAL_FEATURE_NAME,
            "family": "Status Bar",
            "bars": FULL_SIGNAL_BARS,
            "items": [
                StatusBarItem.CellularSignalStrengthStatusBarItem.value,
                StatusBarItem.CellularServiceStatusBarItem.value,
            ],
            "file": FULL_SIGNAL_FILE,
        }

    def describe_active_operations(self) -> list:
        """Active Status Bar operations for summaries/journals.

        The no-SIM feature gets its own named entry; the generic entry's
        count excludes the feature-owned flags so an apply summary never
        double-counts them.
        """
        ops = []
        feature_on = self.is_full_signal_bars_no_sim_enabled()
        if feature_on:
            ops.append(self.describe_full_signal_bars_no_sim())
        generic = self.count_overrides()
        if feature_on:
            # Owned contributions: overrideGSMSignalStrengthBars plus the
            # two overrideItemIsEnabled entries (indices 4 and 6).
            generic -= 3
        if generic > 0:
            ops.append({
                "id": "statusbar.overrides",
                "name": "Status Bar",
                "family": "Status Bar",
                "count": generic,
            })
        return ops


    ### SECONDARY CARRIER
    # CELLULAR SERVICE
    def is_secondary_cellular_service_overridden(self) -> bool:
        return self.is_item_overridden(StatusBarItem.SecondaryCellularServiceStatusBarItem)
    def get_secondary_cellular_service_override(self) -> bool:
        return self.get_item_override(StatusBarItem.SecondaryCellularServiceStatusBarItem)
    def set_secondary_cellular_service(self, shown: bool) -> None:
        overrides = self._overrides()
        idx = StatusBarItem.SecondaryCellularServiceStatusBarItem.value
        overrides.overrideItemIsEnabled[idx] = 1
        overrides.values.itemIsEnabled[idx] = 1 if shown else 0
        overrides.overrideSecondaryCellularConfigured = 1
        overrides.values.secondaryCellularConfigured = 1 if shown else 0
        self._apply_changes(overrides)
    def unset_secondary_cellular_service(self) -> None:
        overrides = self._overrides()
        overrides.overrideItemIsEnabled[StatusBarItem.SecondaryCellularServiceStatusBarItem.value] = 0
        overrides.overrideSecondaryCellularConfigured = 0
        self._apply_changes(overrides)

    # SERVICE STRING
    def is_secondary_carrier_overridden(self) -> bool:
        return self._is_flag_overridden("overrideSecondaryServiceString")
    def get_secondary_carrier_override(self) -> str:
        return self._get_str("secondaryServiceString")
    def set_secondary_carrier_override(self, text: str) -> None:
        overrides = self._overrides()
        truncated = _truncate_utf8(text, 100)
        overrides.values.secondaryServiceString = truncated
        overrides.values.secondaryServiceCrossfadeString = truncated
        self._set_flag("overrideSecondaryServiceString")
    def unset_secondary_carrier_override(self) -> None:
        self._unset_flag("overrideSecondaryServiceString")

    # SERVICE BADGE
    def is_secondary_service_badge_overridden(self) -> bool:
        return self._is_flag_overridden("overrideSecondaryServiceBadgeString")
    def get_secondary_service_badge_override(self) -> str:
        return self._get_str("secondaryServiceBadgeString")
    def set_secondary_service_badge(self, text: str) -> None:
        self._set_flag("overrideSecondaryServiceBadgeString", "secondaryServiceBadgeString", text, max_len=100)
    def unset_secondary_service_badge(self) -> None:
        self._unset_flag("overrideSecondaryServiceBadgeString")

    # DATA NETWORK TYPE
    def is_secondary_data_network_type_overridden(self) -> bool:
        return self._is_flag_overridden("overrideSecondaryDataNetworkType")
    def get_secondary_data_network_type_override(self) -> int:
        return self._get_int("secondaryDataNetworkType")
    def set_secondary_data_network_type(self, id: int) -> None:
        self._set_flag("overrideSecondaryDataNetworkType", "secondaryDataNetworkType", id)
    def unset_secondary_data_network_type(self) -> None:
        self._unset_flag("overrideSecondaryDataNetworkType")

    # GSM SIGNAL BARS
    def is_secondary_gsm_signal_strength_bars_overridden(self) -> bool:
        return self._is_flag_overridden("overrideSecondaryGSMSignalStrengthBars")
    def get_secondary_gsm_signal_strength_bars_override(self) -> int:
        return self._get_int("secondaryGSMSignalStrengthBars")
    def set_secondary_gsm_signal_strength_bars(self, id: int) -> None:
        # NOTE (audit B29): same as primary — never force the icon visible.
        self._set_flag("overrideSecondaryGSMSignalStrengthBars", "secondaryGSMSignalStrengthBars", id)
    def unset_secondary_gsm_signal_strength_bars(self) -> None:
        self._unset_flag("overrideSecondaryGSMSignalStrengthBars")


    ### MISC TEXT INPUTS
    # TIME STRING
    def is_time_overridden(self) -> bool:
        return self._is_flag_overridden("overrideTimeString")
    def get_time_override(self) -> str:
        return self._get_str("timeString")
    def set_time(self, text: str) -> None:
        self._set_flag("overrideTimeString", "timeString", text, max_len=64)
    def unset_time(self) -> None:
        self._unset_flag("overrideTimeString")

    # DATE STRING
    def is_date_overridden(self) -> bool:
        return self._is_flag_overridden("overrideDateString")
    def get_date_override(self) -> str:
        return self._get_str("dateString")
    def set_date(self, text: str) -> None:
        self._set_flag("overrideDateString", "dateString", text, max_len=256)
    def unset_date(self) -> None:
        self._unset_flag("overrideDateString")

    # BREADCRUMB STRING
    def is_crumb_overridden(self) -> bool:
        return self._is_flag_overridden("overrideBreadcrumb")
    def get_crumb_override(self) -> str:
        text = self._get_str("breadcrumbTitle")
        # NOTE (audit): set_crumb() appends the 2-character suffix " ▶"
        # (4 bytes in UTF-8, 2 Python chars after decoding). Stripping 4
        # chars ate 2 characters of the user's own text on every read,
        # compounding on each re-save.
        if len(text) > 1:
            return text[:len(text) - 2]
        return ""
    def set_crumb(self, text: str) -> None:
        overrides = self._overrides()
        overrides.overrideBreadcrumb = 1
        new_crumb = text[:254] + " ▶" if text != "" else ""
        overrides.values.breadcrumbTitle = _truncate_utf8(new_crumb, 256)
        self._apply_changes(overrides)
    def unset_crumb(self) -> None:
        overrides = self._overrides()
        overrides.overrideBreadcrumb = 0
        overrides.values.breadcrumbTitle = "".encode()
        self._apply_changes(overrides)

    # BATTERY DETAIL STRING
    def is_battery_detail_overridden(self) -> bool:
        return self._is_flag_overridden("overrideBatteryDetailString")
    def get_battery_detail_override(self) -> str:
        return self._get_str("batteryDetailString")
    def set_battery_detail(self, text: str) -> None:
        self._set_flag("overrideBatteryDetailString", "batteryDetailString", text, max_len=150)
    def unset_battery_detail(self) -> None:
        self._unset_flag("overrideBatteryDetailString")


    ## MISC SLIDER INPUTS
    # BATTERY CAPACITY
    def is_battery_capacity_overridden(self) -> bool:
        return self._is_flag_overridden("overrideBatteryCapacity")
    def get_battery_capacity_override(self) -> int:
        return self._get_int("batteryCapacity")
    def set_battery_capacity(self, id: int) -> None:
        self._set_flag("overrideBatteryCapacity", "batteryCapacity", id)
    def unset_battery_capacity(self) -> None:
        self._unset_flag("overrideBatteryCapacity")

    # WIFI SIGNAL STRENGTH
    def is_wifi_signal_strength_bars_overridden(self) -> bool:
        return self._is_flag_overridden("overrideWifiSignalStrengthBars")
    def get_wifi_signal_strength_bars_override(self) -> int:
        return self._get_int("wifiSignalStrengthBars")
    def set_wifi_signal_strength_bars(self, id: int) -> None:
        self._set_flag("overrideWifiSignalStrengthBars", "wifiSignalStrengthBars", id)
    def unset_wifi_signal_strength_bars(self) -> None:
        self._unset_flag("overrideWifiSignalStrengthBars")


    ## RAW SIGNAL STRENGTH TOGGLES
    # WIFI
    def is_raw_wifi_signal_shown(self) -> bool:
        return self._is_flag_overridden("overrideDisplayRawWifiSignal")
    def show_raw_wifi_signal(self, shown: bool) -> None:
        overrides = self._overrides()
        overrides.overrideDisplayRawWifiSignal = 1 if shown else 0
        if shown:
            overrides.values.displayRawWifiSignal = 1
        self._apply_changes(overrides)
    # GSM
    def is_raw_gsm_signal_shown(self) -> bool:
        return self._is_flag_overridden("overrideDisplayRawGSMSignal")
    def show_raw_gsm_signal(self, shown: bool) -> None:
        overrides = self._overrides()
        overrides.overrideDisplayRawGSMSignal = 1 if shown else 0
        if shown:
            overrides.values.displayRawGSMSignal = 1
        self._apply_changes(overrides)

    ## RADIO BUTTONS
    def is_item_overridden(self, item: StatusBarItem) -> bool:
        return self._overrides().overrideItemIsEnabled[item.value] == 1
    def get_item_override(self, item: StatusBarItem) -> bool:
        return self._overrides().values.itemIsEnabled[item.value] == 1
    def set_item_override(self, item: StatusBarItem, shown: bool) -> None:
        overrides = self._overrides()
        overrides.overrideItemIsEnabled[item.value] = 1
        overrides.values.itemIsEnabled[item.value] = 1 if shown else 0
        self._apply_changes(overrides)
    def unset_item_override(self, item: StatusBarItem) -> None:
        overrides = self._overrides()
        overrides.overrideItemIsEnabled[item.value] = 0
        self._apply_changes(overrides)


    def is_silly_mode_enabled(self) -> bool:
        return self.setter.silly_mode
    def toggle_silly_mode(self, value: bool) -> None:
        self.setter.silly_mode = value

    def count_overrides(self) -> int:
        """Number of currently-active overrides (drives the apply summary).

        Counts every ``override*`` flag set to 1 plus every enabled
        ``overrideItemIsEnabled`` entry. Approximate by design — a single
        user change can legitimately toggle more than one override field.
        """
        overrides = self._overrides()
        count = 0
        try:
            for i in range(len(overrides.overrideItemIsEnabled)):
                if overrides.overrideItemIsEnabled[i]:
                    count += 1
        except Exception:
            pass
        for name in dir(overrides):
            if not name.startswith("override") or name == "overrideItemIsEnabled":
                continue
            try:
                val = getattr(overrides, name)
            except Exception:
                continue
            if isinstance(val, int) and val:
                count += 1
        return count