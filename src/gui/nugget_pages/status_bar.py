"""Status Bar page, Full Nugget shell.

Verbatim port of leminlimez/Nugget v7.4.1
``src/gui/pages/tools/status_bar.py`` (imports and class name aside):
every control of the vendored form is wired exactly as upstream wires
it, and the final ``load_status_bar()`` reflects the live overrides.
That works unchanged because this app's ``StatusBarTweak`` still
carries upstream's full override API (set_time/unset_time,
show_raw_wifi_signal, set_item_override, toggle_silly_mode, ...).

Audit 26 (2026-10-09): the vendored ``load_status_bar()`` never loaded
back the master switch, the date override, or the item-visibility
radio groups, so active state looked OFF. Those loads are completed
below (marked inline); the wiring above is untouched.
"""

from src.gui.pages.page import Page
from src.qt.nugget741_ui import Ui_Nugget741

from src.tweaks.tweaks import tweaks, TweakID
from src.tweaks.status_bar.status_setter import StatusBarItem

class NuggetStatusBarPage(Page):
    def __init__(self, ui: Ui_Nugget741):
        super().__init__()
        self.ui = ui
        self.status_manager = tweaks[TweakID.StatusBar]

    def load_page(self):
        self.ui.statusBarEnabledChk.toggled.connect(self.on_statusBarEnabledChk_toggled)
        # PRIMARY CARRIER
        self.ui.pDefaultRdo.clicked.connect(self.on_pDefaultRdo_clicked)
        self.ui.pShowRdo.clicked.connect(self.on_pShowRdo_clicked)
        self.ui.pHideRdo.clicked.connect(self.on_pHideRdo_clicked)
        self.ui.pCarrierChk.toggled.connect(self.on_pCarrierChk_clicked)
        self.ui.pCarrierTxt.textEdited.connect(self.on_pCarrierTxt_textEdited)
        self.ui.pBadgeChk.toggled.connect(self.on_pBadgeChk_clicked)
        self.ui.pBadgeTxt.textEdited.connect(self.on_pBadgeTxt_textEdited)
        self.ui.pTypeChk.toggled.connect(self.on_pTypeChk_clicked)
        self.ui.pTypeDrp.activated.connect(self.on_pTypeDrp_activated)
        self.ui.pStrengthChk.toggled.connect(self.on_pStrengthChk_clicked)
        self.ui.pStrengthSld.sliderMoved.connect(self.on_pStrengthSld_sliderMoved)
        # SECONDARY CARRIER
        self.ui.sDefaultRdo.clicked.connect(self.on_sDefaultRdo_clicked)
        self.ui.sShowRdo.clicked.connect(self.on_sShowRdo_clicked)
        self.ui.sHideRdo.clicked.connect(self.on_sHideRdo_clicked)
        self.ui.sCarrierChk.toggled.connect(self.on_sCarrierChk_clicked)
        self.ui.sCarrierTxt.textEdited.connect(self.on_sCarrierTxt_textEdited)
        self.ui.sBadgeChk.toggled.connect(self.on_sBadgeChk_clicked)
        self.ui.sBadgeTxt.textEdited.connect(self.on_sBadgeTxt_textEdited)
        self.ui.sTypeChk.toggled.connect(self.on_sTypeChk_clicked)
        self.ui.sTypeDrp.activated.connect(self.on_sTypeDrp_activated)
        self.ui.sStrengthChk.toggled.connect(self.on_sStrengthChk_clicked)
        self.ui.sStrengthSld.sliderMoved.connect(self.on_sStrengthSld_sliderMoved)
        # MISC TEXT INPUTS
        self.ui.timeChk.clicked.connect(self.on_timeChk_clicked)
        self.ui.timeTxt.textEdited.connect(self.on_timeTxt_textEdited)
        self.ui.dateChk.clicked.connect(self.on_dateChk_clicked)
        self.ui.dateTxt.textEdited.connect(self.on_dateTxt_textEdited)
        self.ui.breadcrumbChk.clicked.connect(self.on_breadcrumbChk_clicked)
        self.ui.breadcrumbTxt.textEdited.connect(self.on_breadcrumbTxt_textEdited)
        self.ui.batteryDetailChk.clicked.connect(self.on_batteryDetailChk_clicked)
        self.ui.batteryDetailTxt.textEdited.connect(self.on_batteryDetailTxt_textEdited)
        # MISC SLIDER INPUTS
        self.ui.batteryCapacityChk.clicked.connect(self.on_batteryCapacityChk_clicked)
        self.ui.batteryCapacitySld.sliderMoved.connect(self.on_batteryCapacitySld_sliderMoved)
        self.ui.wifiStrengthChk.clicked.connect(self.on_wifiStrengthChk_clicked)
        self.ui.wifiStrengthSld.sliderMoved.connect(self.on_wifiStrengthSld_sliderMoved)
        # RAW SIGNAL STRENGTH INPUTS
        self.ui.numericWifiChk.clicked.connect(self.on_numericWifiChk_clicked)
        self.ui.numericCellChk.clicked.connect(self.on_numericCellChk_clicked)


        # RADIO BUTTON INPUTS
        self.ui.dndDefaultRdo.clicked.connect(lambda _: self.on_defaultRdo_clicked(StatusBarItem.QuietModeStatusBarItem))
        self.ui.dndShowRdo.clicked.connect(lambda _: self.on_showRdo_clicked(StatusBarItem.QuietModeStatusBarItem))
        self.ui.dndHideRdo.clicked.connect(lambda _: self.on_hideRdo_clicked(StatusBarItem.QuietModeStatusBarItem))

        self.ui.airplaneDefaultRdo.clicked.connect(lambda _: self.on_defaultRdo_clicked(StatusBarItem.AirplaneModeStatusBarItem))
        self.ui.airplaneShowRdo.clicked.connect(lambda _: self.on_showRdo_clicked(StatusBarItem.AirplaneModeStatusBarItem))
        self.ui.airplaneHideRdo.clicked.connect(lambda _: self.on_hideRdo_clicked(StatusBarItem.AirplaneModeStatusBarItem))

        self.ui.wifiDefaultRdo.clicked.connect(lambda _: self.on_defaultRdo_clicked(StatusBarItem.CellularDataNetworkStatusBarItem))
        self.ui.wifiShowRdo.clicked.connect(lambda _: self.on_showRdo_clicked(StatusBarItem.CellularDataNetworkStatusBarItem))
        self.ui.wifiHideRdo.clicked.connect(lambda _: self.on_hideRdo_clicked(StatusBarItem.CellularDataNetworkStatusBarItem))

        self.ui.batteryDefaultRdo.clicked.connect(lambda _: self.on_defaultRdo_clicked(StatusBarItem.MainBatteryStatusBarItem))
        self.ui.batteryShowRdo.clicked.connect(lambda _: self.on_showRdo_clicked(StatusBarItem.MainBatteryStatusBarItem))
        self.ui.batteryHideRdo.clicked.connect(lambda _: self.on_hideRdo_clicked(StatusBarItem.MainBatteryStatusBarItem))

        self.ui.bluetoothDefaultRdo.clicked.connect(lambda _: self.on_defaultRdo_clicked(StatusBarItem.BluetoothStatusBarItem))
        self.ui.bluetoothShowRdo.clicked.connect(lambda _: self.on_showRdo_clicked(StatusBarItem.BluetoothStatusBarItem))
        self.ui.bluetoothHideRdo.clicked.connect(lambda _: self.on_hideRdo_clicked(StatusBarItem.BluetoothStatusBarItem))

        self.ui.alarmDefaultRdo.clicked.connect(lambda _: self.on_defaultRdo_clicked(StatusBarItem.AlarmStatusBarItem))
        self.ui.alarmShowRdo.clicked.connect(lambda _: self.on_showRdo_clicked(StatusBarItem.AlarmStatusBarItem))
        self.ui.alarmHideRdo.clicked.connect(lambda _: self.on_hideRdo_clicked(StatusBarItem.AlarmStatusBarItem))

        self.ui.locationDefaultRdo.clicked.connect(lambda _: self.on_defaultRdo_clicked(StatusBarItem.LocationStatusBarItem))
        self.ui.locationShowRdo.clicked.connect(lambda _: self.on_showRdo_clicked(StatusBarItem.LocationStatusBarItem))
        self.ui.locationHideRdo.clicked.connect(lambda _: self.on_hideRdo_clicked(StatusBarItem.LocationStatusBarItem))

        self.ui.rotationDefaultRdo.clicked.connect(lambda _: self.on_defaultRdo_clicked(StatusBarItem.RotationLockStatusBarItem))
        self.ui.rotationShowRdo.clicked.connect(lambda _: self.on_showRdo_clicked(StatusBarItem.RotationLockStatusBarItem))
        self.ui.rotationHideRdo.clicked.connect(lambda _: self.on_hideRdo_clicked(StatusBarItem.RotationLockStatusBarItem))

        self.ui.airplayDefaultRdo.clicked.connect(lambda _: self.on_defaultRdo_clicked(StatusBarItem.AirPlayStatusBarItem))
        self.ui.airplayShowRdo.clicked.connect(lambda _: self.on_showRdo_clicked(StatusBarItem.AirPlayStatusBarItem))
        self.ui.airplayHideRdo.clicked.connect(lambda _: self.on_hideRdo_clicked(StatusBarItem.AirPlayStatusBarItem))

        self.ui.carplayDefaultRdo.clicked.connect(lambda _: self.on_defaultRdo_clicked(StatusBarItem.CarPlayStatusBarItem))
        self.ui.carplayShowRdo.clicked.connect(lambda _: self.on_showRdo_clicked(StatusBarItem.CarPlayStatusBarItem))
        self.ui.carplayHideRdo.clicked.connect(lambda _: self.on_hideRdo_clicked(StatusBarItem.CarPlayStatusBarItem))

        self.ui.vpnDefaultRdo.clicked.connect(lambda _: self.on_defaultRdo_clicked(StatusBarItem.VPNStatusBarItem))
        self.ui.vpnShowRdo.clicked.connect(lambda _: self.on_showRdo_clicked(StatusBarItem.VPNStatusBarItem))
        self.ui.vpnHideRdo.clicked.connect(lambda _: self.on_hideRdo_clicked(StatusBarItem.VPNStatusBarItem))

        self.ui.studentDefaultRdo.clicked.connect(lambda _: self.on_defaultRdo_clicked(StatusBarItem.StudentStatusBarItem))
        self.ui.studentShowRdo.clicked.connect(lambda _: self.on_showRdo_clicked(StatusBarItem.StudentStatusBarItem))
        self.ui.studentHideRdo.clicked.connect(lambda _: self.on_hideRdo_clicked(StatusBarItem.StudentStatusBarItem))

        # TODO: Fix this and VC not showing
        self.ui.waterDefaultRdo.clicked.connect(lambda _: self.on_defaultRdo_clicked(StatusBarItem.LiquidDetectionStatusBarItem))
        self.ui.waterShowRdo.clicked.connect(lambda _: self.on_showRdo_clicked(StatusBarItem.LiquidDetectionStatusBarItem))
        self.ui.waterHideRdo.clicked.connect(lambda _: self.on_hideRdo_clicked(StatusBarItem.LiquidDetectionStatusBarItem))

        self.ui.vcDefaultRdo.clicked.connect(lambda _: self.on_defaultRdo_clicked(StatusBarItem.VoiceControlStatusBarItem))
        self.ui.vcShowRdo.clicked.connect(lambda _: self.on_showRdo_clicked(StatusBarItem.VoiceControlStatusBarItem))
        self.ui.vcHideRdo.clicked.connect(lambda _: self.on_hideRdo_clicked(StatusBarItem.VoiceControlStatusBarItem))
        
        self.ui.sillyModeChk.clicked.connect(self.on_sillyModeChk_clicked)

        self.load_status_bar()


    ## PAGE ACTIONS
    def on_statusBarEnabledChk_toggled(self, checked: bool):
        self.ui.statusBarPageContent.setDisabled(not checked)
        self.status_manager.set_enabled(checked)

    # PRIMARY CARRIER
    def on_pDefaultRdo_clicked(self):
        self.status_manager.unset_cellular_service()
    def on_pShowRdo_clicked(self):
        self.status_manager.set_cellular_service(True)
    def on_pHideRdo_clicked(self):
        self.status_manager.set_cellular_service(False)
    def on_pCarrierChk_clicked(self, checked: bool):
        if checked:
            self.status_manager.set_carrier_override(str(self.ui.pCarrierTxt.text()))
        else:
            self.status_manager.unset_carrier_override()
    def on_pCarrierTxt_textEdited(self, text: str):
        if self.ui.pCarrierChk.isChecked():
            self.status_manager.set_carrier_override(text)
    def on_pBadgeChk_clicked(self, checked: bool):
        if checked:
            self.status_manager.set_primary_service_badge(str(self.ui.pBadgeTxt.text()))
        else:
            self.status_manager.unset_primary_service_badge()
    def on_pBadgeTxt_textEdited(self, text: str):
        if self.ui.pBadgeChk.isChecked():
            self.status_manager.set_primary_service_badge(text)
    def on_pTypeChk_clicked(self, checked: bool):
        if checked:
            self.status_manager.set_data_network_type(self.ui.pTypeDrp.currentIndex())
        else:
            self.status_manager.unset_data_network_type()
    def on_pTypeDrp_activated(self, index: int):
        if self.ui.pTypeChk.isChecked():
            self.status_manager.set_data_network_type(self.ui.pTypeDrp.currentIndex())
    def on_pStrengthChk_clicked(self, checked: bool):
        if checked:
            self.status_manager.set_gsm_signal_strength_bars(self.ui.pStrengthSld.value())
        else:
            self.status_manager.unset_gsm_signal_strength_bars()
    def on_pStrengthSld_sliderMoved(self, pos: int):
        self.ui.pStrengthLbl.setText(str(pos) + (" Bar" if pos == 1 else " Bars"))
        if self.ui.pStrengthChk.isChecked():
            self.status_manager.set_gsm_signal_strength_bars(pos)

    # SECONDARY CARRIER
    def on_sDefaultRdo_clicked(self):
        self.status_manager.unset_secondary_cellular_service()
    def on_sShowRdo_clicked(self):
        self.status_manager.set_secondary_cellular_service(True)
    def on_sHideRdo_clicked(self):
        self.status_manager.set_secondary_cellular_service(False)
    def on_sCarrierChk_clicked(self, checked: bool):
        if checked:
            self.status_manager.set_secondary_carrier_override(str(self.ui.sCarrierTxt.text()))
        else:
            self.status_manager.unset_secondary_carrier_override()
    def on_sCarrierTxt_textEdited(self, text: str):
        if self.ui.sCarrierChk.isChecked():
            self.status_manager.set_secondary_carrier_override(text)
    def on_sBadgeChk_clicked(self, checked: bool):
        if checked:
            self.status_manager.set_secondary_service_badge(str(self.ui.sBadgeTxt.text()))
        else:
            self.status_manager.unset_secondary_service_badge()
    def on_sBadgeTxt_textEdited(self, text: str):
        if self.ui.sBadgeChk.isChecked():
            self.status_manager.set_secondary_service_badge(text)
    def on_sTypeChk_clicked(self, checked: bool):
        if checked:
            self.status_manager.set_secondary_data_network_type(self.ui.sTypeDrp.currentIndex())
        else:
            self.status_manager.unset_secondary_data_network_type()
    def on_sTypeDrp_activated(self, index: int):
        if self.ui.sTypeChk.isChecked():
            self.status_manager.set_secondary_data_network_type(index)
    def on_sStrengthChk_clicked(self, checked: bool):
        if checked:
            self.status_manager.set_secondary_gsm_signal_strength_bars(self.ui.sStrengthSld.value())
        else:
            self.status_manager.unset_secondary_gsm_signal_strength_bars()
    def on_sStrengthSld_sliderMoved(self, pos: int):
        self.ui.sStrengthLbl.setText(str(pos) + (" Bar" if pos == 1 else " Bars"))
        if self.ui.sStrengthChk.isChecked():
            self.status_manager.set_secondary_gsm_signal_strength_bars(pos)

    # Misc Text Inputs
    def on_timeChk_clicked(self, checked: bool):
        if checked:
            self.status_manager.set_time(self.ui.timeTxt.text())
        else:
            self.status_manager.unset_time()
    def on_timeTxt_textEdited(self, text: str):
        if self.ui.timeChk.isChecked():
            self.status_manager.set_time(text)

    def on_dateChk_clicked(self, checked: bool):
        if checked:
            self.status_manager.set_date(self.ui.dateTxt.text())
        else:
            self.status_manager.unset_date()
    def on_dateTxt_textEdited(self, text: str):
        if self.ui.dateChk.isChecked():
            self.status_manager.set_date(text)

    def on_breadcrumbChk_clicked(self, checked: bool):
        if checked:
            self.status_manager.set_crumb(self.ui.breadcrumbTxt.text())
        else:
            self.status_manager.unset_crumb()
    def on_breadcrumbTxt_textEdited(self, text: str):
        if self.ui.breadcrumbChk.isChecked():
            self.status_manager.set_crumb(text)

    def on_batteryDetailChk_clicked(self, checked: bool):
        if checked:
            self.status_manager.set_battery_detail(self.ui.batteryDetailTxt.text())
        else:
            self.status_manager.unset_battery_detail()
    def on_batteryDetailTxt_textEdited(self, text: str):
        if self.ui.batteryDetailChk.isChecked():
            self.status_manager.set_battery_detail(text)

    # Misc Slider Inputs
    def on_batteryCapacityChk_clicked(self, checked: bool):
        if checked:
            self.status_manager.set_battery_capacity(self.ui.batteryCapacitySld.value())
        else:
            self.status_manager.unset_battery_capacity()
    def on_batteryCapacitySld_sliderMoved(self, pos: int):
        self.ui.batteryCapacityLbl.setText(str(pos) + "%")
        if self.ui.batteryCapacityChk.isChecked():
            self.status_manager.set_battery_capacity(pos)

    def on_wifiStrengthChk_clicked(self, checked: bool):
        if checked:
            self.status_manager.set_wifi_signal_strength_bars(self.ui.wifiStrengthSld.value())
        else:
            self.status_manager.unset_wifi_signal_strength_bars()
    def on_wifiStrengthSld_sliderMoved(self, pos: int):
        self.ui.wifiStrengthLbl.setText(str(pos) + (" Bar" if pos == 1 else " Bars"))
        if self.ui.wifiStrengthChk.isChecked():
            self.status_manager.set_wifi_signal_strength_bars(pos)

    # Raw Signal Strength Inputs
    def on_numericWifiChk_clicked(self, checked: bool):
        self.status_manager.show_raw_wifi_signal(checked)
    def on_numericCellChk_clicked(self, checked: bool):
        self.status_manager.show_raw_gsm_signal(checked)

    # Hiding Option Inputs
    def on_defaultRdo_clicked(self, item: StatusBarItem):
        self.status_manager.unset_item_override(item)
    def on_showRdo_clicked(self, item: StatusBarItem):
        self.status_manager.set_item_override(item, True)
    def on_hideRdo_clicked(self, item: StatusBarItem):
        self.status_manager.set_item_override(item, False)

    def on_sillyModeChk_clicked(self, checked: bool):
        self.status_manager.toggle_silly_mode(checked)

        
    ## LOADING STATUS BAR
    def _load_item_radios(self, item: StatusBarItem, default_rdo, show_rdo, hide_rdo):
        # Audit 26: reflect the live item override — Default when the
        # item is not overridden, Force Show/Hide per its stored value.
        if not self.status_manager.is_item_overridden(item):
            chosen = default_rdo
        elif self.status_manager.get_item_override(item):
            chosen = show_rdo
        else:
            chosen = hide_rdo
        for rdo in (default_rdo, show_rdo, hide_rdo):
            rdo.setChecked(rdo is chosen)

    def load_status_bar(self):
        # Audit 26: master switch + content gating were never loaded.
        self.ui.statusBarEnabledChk.setChecked(self.status_manager.enabled)
        self.ui.statusBarPageContent.setDisabled(not self.status_manager.enabled)
        # Load primary carrier settings
        if self.status_manager.is_cellular_service_overridden():
            if self.status_manager.get_cellular_service_override():
                self.ui.pShowRdo.setChecked(True)
            else:
                self.ui.pHideRdo.setChecked(True)
        else:
            self.ui.pDefaultRdo.setChecked(True)
        self.ui.pCarrierChk.setChecked(self.status_manager.is_carrier_overridden())
        self.ui.pCarrierTxt.setText(self.status_manager.get_carrier_override())
        self.ui.pBadgeChk.setChecked(self.status_manager.is_primary_service_badge_overridden())
        self.ui.pBadgeTxt.setText(self.status_manager.get_primary_service_badge_override())
        self.ui.pTypeChk.setChecked(self.status_manager.is_data_network_type_overridden())
        self.ui.pTypeDrp.setCurrentIndex(self.status_manager.get_data_network_type_override())
        self.ui.pStrengthChk.setChecked(self.status_manager.is_gsm_signal_strength_bars_overridden())
        pos: int = self.status_manager.get_gsm_signal_strength_bars_override()
        self.ui.pStrengthSld.setValue(pos)
        self.ui.pStrengthLbl.setText(str(pos) + (" Bar" if pos == 1 else " Bars"))

        # Load secondary carrier settings
        if self.status_manager.is_secondary_cellular_service_overridden():
            if self.status_manager.get_secondary_cellular_service_override():
                self.ui.sShowRdo.setChecked(True)
            else:
                self.ui.sHideRdo.setChecked(True)
        else:
            self.ui.sDefaultRdo.setChecked(True)
        self.ui.sCarrierChk.setChecked(self.status_manager.is_secondary_carrier_overridden())
        self.ui.sCarrierTxt.setText(self.status_manager.get_secondary_carrier_override())
        self.ui.sBadgeChk.setChecked(self.status_manager.is_secondary_service_badge_overridden())
        self.ui.sBadgeTxt.setText(self.status_manager.get_secondary_service_badge_override())
        self.ui.sTypeChk.setChecked(self.status_manager.is_secondary_data_network_type_overridden())
        self.ui.sTypeDrp.setCurrentIndex(self.status_manager.get_secondary_data_network_type_override())
        self.ui.sStrengthChk.setChecked(self.status_manager.is_secondary_gsm_signal_strength_bars_overridden())
        pos = self.status_manager.get_secondary_gsm_signal_strength_bars_override()
        self.ui.sStrengthSld.setValue(pos)
        self.ui.sStrengthLbl.setText(str(pos) + (" Bar" if pos == 1 else " Bars"))

        # Load misc text inputs
        self.ui.timeChk.setChecked(self.status_manager.is_time_overridden())
        self.ui.timeTxt.setText(self.status_manager.get_time_override())
        # Audit 26: the date override was never loaded back.
        self.ui.dateChk.setChecked(self.status_manager.is_date_overridden())
        self.ui.dateTxt.setText(self.status_manager.get_date_override())
        self.ui.breadcrumbChk.setChecked(self.status_manager.is_crumb_overridden())
        self.ui.breadcrumbTxt.setText(self.status_manager.get_crumb_override())
        self.ui.batteryDetailChk.setChecked(self.status_manager.is_battery_detail_overridden())
        self.ui.batteryDetailTxt.setText(self.status_manager.get_battery_detail_override())

        # Load misc slider inputs
        self.ui.batteryCapacityChk.setChecked(self.status_manager.is_battery_capacity_overridden())
        pos = self.status_manager.get_battery_capacity_override()
        self.ui.batteryCapacitySld.setValue(pos)
        self.ui.batteryCapacityLbl.setText(str(pos) + "%")
        self.ui.wifiStrengthChk.setChecked(self.status_manager.is_wifi_signal_strength_bars_overridden())
        pos = self.status_manager.get_wifi_signal_strength_bars_override()
        self.ui.wifiStrengthSld.setValue(pos)
        self.ui.wifiStrengthLbl.setText(str(pos) + (" Bar" if pos == 1 else " Bars"))

        # Load raw signal strength inputs
        self.ui.numericWifiChk.setChecked(self.status_manager.is_raw_wifi_signal_shown())
        self.ui.numericCellChk.setChecked(self.status_manager.is_raw_gsm_signal_shown())

        # Audit 26: item-visibility radio groups were never loaded back.
        ui = self.ui
        self._load_item_radios(StatusBarItem.QuietModeStatusBarItem,
                               ui.dndDefaultRdo, ui.dndShowRdo, ui.dndHideRdo)
        self._load_item_radios(StatusBarItem.AirplaneModeStatusBarItem,
                               ui.airplaneDefaultRdo, ui.airplaneShowRdo, ui.airplaneHideRdo)
        self._load_item_radios(StatusBarItem.CellularDataNetworkStatusBarItem,
                               ui.wifiDefaultRdo, ui.wifiShowRdo, ui.wifiHideRdo)
        self._load_item_radios(StatusBarItem.MainBatteryStatusBarItem,
                               ui.batteryDefaultRdo, ui.batteryShowRdo, ui.batteryHideRdo)
        self._load_item_radios(StatusBarItem.BluetoothStatusBarItem,
                               ui.bluetoothDefaultRdo, ui.bluetoothShowRdo, ui.bluetoothHideRdo)
        self._load_item_radios(StatusBarItem.AlarmStatusBarItem,
                               ui.alarmDefaultRdo, ui.alarmShowRdo, ui.alarmHideRdo)
        self._load_item_radios(StatusBarItem.LocationStatusBarItem,
                               ui.locationDefaultRdo, ui.locationShowRdo, ui.locationHideRdo)
        self._load_item_radios(StatusBarItem.RotationLockStatusBarItem,
                               ui.rotationDefaultRdo, ui.rotationShowRdo, ui.rotationHideRdo)
        self._load_item_radios(StatusBarItem.AirPlayStatusBarItem,
                               ui.airplayDefaultRdo, ui.airplayShowRdo, ui.airplayHideRdo)
        self._load_item_radios(StatusBarItem.CarPlayStatusBarItem,
                               ui.carplayDefaultRdo, ui.carplayShowRdo, ui.carplayHideRdo)
        self._load_item_radios(StatusBarItem.VPNStatusBarItem,
                               ui.vpnDefaultRdo, ui.vpnShowRdo, ui.vpnHideRdo)
        self._load_item_radios(StatusBarItem.StudentStatusBarItem,
                               ui.studentDefaultRdo, ui.studentShowRdo, ui.studentHideRdo)
        self._load_item_radios(StatusBarItem.LiquidDetectionStatusBarItem,
                               ui.waterDefaultRdo, ui.waterShowRdo, ui.waterHideRdo)
        self._load_item_radios(StatusBarItem.VoiceControlStatusBarItem,
                               ui.vcDefaultRdo, ui.vcShowRdo, ui.vcHideRdo)

        # Load hiding option inputs
        self.ui.sillyModeChk.setChecked(self.status_manager.is_silly_mode_enabled())