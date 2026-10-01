from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import QCoreApplication

try:
    from shiboken6 import isValid as _shiboken_is_valid
except Exception:
    # Non-*/shiboken-less environments (some frozen builds) always report valid.
    _shiboken_is_valid = lambda _obj: True


def _still_running(worker) -> bool:
    """True when ``worker`` is a live QThread still executing.

    These workers all wire ``finished -> deleteLater``, which frees the C++
    object before the window ever drops its stored reference — so a saved
    worker can already be a dead shiboken wrapper. Probing that wrapper
    raises ``RuntimeError`` ("Internal C++ object already deleted"), which
    must never escape from a closeEvent.
    """
    if worker is None:
        return False
    try:
        if not _shiboken_is_valid(worker):
            return False
        return worker.isRunning()
    except RuntimeError:
        return False

from src.qt.mainwindow_ui import Ui_Nugget
import src.gui.pages as Pages

from src.controllers.translator import Translator
from src.controllers.preset_manager import PresetManager

from src.gui.pages.pages_list import Page

if TYPE_CHECKING:
    from src.devicemanagement.device_manager import DeviceManager

from src.gui.ios.theme_manager import ThemeManager
from src.gui.ios.home import IOSHomePage
from src.gui.ios.tweaks import IOSTweaksPage, IOSSectionPage
from src.gui.ios.posterboard import IOSPosterboardPage
from src.gui.ios.daemons import IOSDaemonsPage
from src.gui.ios.mobilegestalt import IOSMobileGestaltPage
from src.gui.ios.apply import IOSApplyPage
from src.gui.ios.settings import IOSSettingsPage
from src.gui.ios.statusbar import IOSStatusBarPage
from src.gui.ios.icon_themes import IOSIconThemesPage
from src.gui.ios.passcode_theme import IOSPasscodeThemePage
from src.tweaks.registry import Section

from src.gui.theme import ColorThemeManager, t, theme_icon, themed_stylesheet

from src.gui.main_window_mixins import (
    ApplyMixin,
    DeviceBarMixin,
    NavigationMixin,
    SettingsMixin,
)

# Classic chrome (device bar + sidebar + home toolbar) uses monochrome white
# bootstrap SVGs; they must be recolored on every theme change.
_HIDDEN_THEMED_ICONS = {
    "phoneIconBtn": ":/icon/phone.svg",
    "refreshBtn": ":/icon/arrow-clockwise.svg",
    "homePageBtn": ":/icon/house.svg",
    "gestaltPageBtn": ":/icon/iphone-island.svg",
    "euEnablerPageBtn": ":/icon/geo-alt.svg",
    "statusBarPageBtn": ":/icon/wifi.svg",
    "passcodePageBtn": ":/icon/lock.svg",
    "springboardOptionsPageBtn": ":/icon/app-indicator.svg",
    "internalOptionsPageBtn": ":/icon/hdd.svg",
    "liquidGlassPageBtn": ":/icon/liquid-glass.svg",
    "daemonsPageBtn": ":/icon/toggles.svg",
    "iconThemesPageBtn": ":/icon/brush.svg",
    "applyPageBtn": ":/icon/check-circle.svg",
    "posterboardPageBtn": ":/icon/wallpaper.svg",
    "settingsPageBtn": ":/icon/gear.svg",
    "mainDevBtn": ":/icon/github.svg",
    "discordBtn": ":/icon/discord.svg",
    "starOnGithubBtn": ":/icon/star.svg",
    "leminGithubBtn": ":/icon/github.svg",
    "leminTwitterBtn": ":/icon/twitter.svg",
    "leminKoFiBtn": ":/icon/currency-dollar.svg",
}

# Classic home "credits" buttons that hardcode dark borders in the .ui.
_HIDDEN_BORDERED_BTNS = [
    "helpFromBtn", "posterRestoreBtn", "snoolieBtn", "disfordottieBtn",
    "mikasaBtn", "wind0ws11AeroBtn", "translatorsBtn", "libiBtn",
    "duyBtn", "jjtechBtn", "qtBtn",
]

class MainWindow(QtWidgets.QMainWindow, DeviceBarMixin, SettingsMixin,
                 NavigationMixin, ApplyMixin):
    def __init__(self, device_manager: "DeviceManager", translator: Translator):
        super(MainWindow, self).__init__()
        self.device_manager = device_manager
        self.translator = translator
        # WorkSlop app icon (flask). Falls back silently when running from a
        # source tree without the generated icon next to the repo root.
        try:
            import sys as _sys
            from pathlib import Path as _Path
            _candidates = [
                _Path(__file__).resolve().parents[2] / "workslop_icon.png",
            ]
            # PyInstaller bundle: data files land under sys._MEIPASS.
            _meipass = getattr(_sys, "_MEIPASS", None)
            if _meipass:
                _candidates.insert(0, _Path(_meipass) / "workslop_icon.png")
            for _icon_path in _candidates:
                if _icon_path.is_file():
                    self.setWindowIcon(QtGui.QIcon(str(_icon_path)))
                    break
        except Exception:
            pass
        self.settings = self.translator.settings
        self.ui = Ui_Nugget()
        self.ui.setupUi(self)
        self.noneText = self.tr("None")
        self.apply_in_progress = False
        self.refresh_in_progress = False
        self._cache_restore_in_progress = False
        self._cache_restore_thread = None
        self.threadpool = QtCore.QThreadPool()

        self.preset_manager = PresetManager()
        self._preset_autosave_pending = False

        self.loadSettings()
        self._load_last_preset()
        self._register_tweak_autosave()

        self.initial_load = True

        # hide every page
        self.ui.posterboardPageBtn.hide()
        self.ui.euEnablerPageBtn.hide()
        self.ui.statusBarPageBtn.hide()
        self.ui.springboardOptionsPageBtn.hide()
        self.ui.internalOptionsPageBtn.hide()
        self.ui.liquidGlassPageBtn.hide()
        self.ui.daemonsPageBtn.hide()
        self.ui.iconThemesPageBtn.hide()
        self.ui.passcodePageBtn.hide()
        self.ui.applyPageBtn.hide()
        self.ui.sidebarDiv1.hide()
        self.ui.sidebarDiv2.hide()

        # pre-load the pages
        self.pages = {
            Page.Home: Pages.Home(window=self, ui=self.ui),
            Page.Daemons: Pages.Daemons(ui=self.ui, window=self)
        }

        # theme manager stores the active UI mode (classic sidebar shell vs
        # full-screen iOS); apply_theme() below applies it
        self.theme_manager = ThemeManager(self)

        # Color theme manager (dark/light + accent)
        self._color_theme = ColorThemeManager.instance()
        self._color_theme.theme_changed.connect(self._on_color_theme_changed)

        # build the iOS-style pages stack
        # 0 = home, 1 = tweaks, 2 = posterboard, 3 = daemons, 4 = settings,
        # 5 = statusbar, 6 = apply, 7 = springboard, 8 = internal, 9 = liquidglass,
        # 10 = icon themes, 11 = passcode themes
        self.ios_pages = QtWidgets.QStackedWidget(self)
        self.ios_pages.setStyleSheet(t("page_bg"))
        self.ios_home = IOSHomePage(self)
        self.ios_tweaks = IOSTweaksPage(self)
        self.ios_posterboard = IOSPosterboardPage(self)
        self.ios_daemons = IOSDaemonsPage(self)
        self.ios_settings = IOSSettingsPage(self)
        self.ios_statusbar = IOSStatusBarPage(self)
        self.ios_apply = IOSApplyPage(self)
        self.ios_springboard = IOSSectionPage(self, Section.SPRINGBOARD)
        self.ios_internal = IOSSectionPage(self, Section.INTERNAL)
        self.ios_liquidglass = IOSSectionPage(self, Section.LIQUID_GLASS)
        self.ios_iconthemes = IOSIconThemesPage(self)
        self.ios_passthemes = IOSPasscodeThemePage(self)
        self.ios_gestalt = IOSMobileGestaltPage(self)
        from src.gui.ios.backup import IOSBackupPage
        from src.gui.ios.themes_hub import IOSThemesHubPage
        from src.gui.ios.appdata import IOSAppDataPage
        self.ios_backup = IOSBackupPage(self)
        self.ios_themes_hub = IOSThemesHubPage(self)
        self.ios_appdata = IOSAppDataPage(self)
        self.ios_pages.addWidget(self.ios_home)
        self.ios_pages.addWidget(self.ios_tweaks)
        self.ios_pages.addWidget(self.ios_posterboard)
        self.ios_pages.addWidget(self.ios_daemons)
        self.ios_pages.addWidget(self.ios_settings)
        self.ios_pages.addWidget(self.ios_statusbar)
        self.ios_pages.addWidget(self.ios_apply)
        self.ios_pages.addWidget(self.ios_springboard)
        self.ios_pages.addWidget(self.ios_internal)
        self.ios_pages.addWidget(self.ios_liquidglass)
        self.ios_pages.addWidget(self.ios_iconthemes)
        self.ios_pages.addWidget(self.ios_passthemes)
        self.ios_pages.addWidget(self.ios_gestalt)
        # WorkSlop menus: appended at the end so no existing page index shifts.
        # 13 = backup, 14 = themes hub, 15 = app data.
        self.ios_pages.addWidget(self.ios_backup)
        self.ios_pages.addWidget(self.ios_themes_hub)
        self.ios_pages.addWidget(self.ios_appdata)

        # Shared reusable header: one instance for every iOS subpage,
        # reconfigured on page change (title / back / right action).
        from src.gui.ios.components import IOSNavBar
        self.ios_nav = IOSNavBar("", on_back=self._go_back)
        self._ios_page_titles = {
            0: "WorkSlop Desktop",
            1: QtCore.QCoreApplication.translate("Nugget", "Tweaks"),
            2: "PosterBoard",
            3: QtCore.QCoreApplication.translate("Nugget", "Daemons"),
            4: QtCore.QCoreApplication.translate("Nugget", "Settings"),
            5: QCoreApplication.translate("Nugget", "Status Bar"),
            6: QCoreApplication.translate("Nugget", "Apply"),
            7: QtCore.QCoreApplication.translate("Nugget", "SpringBoard"),
            8: QtCore.QCoreApplication.translate("Nugget", "Internal"),
            9: QtCore.QCoreApplication.translate("Nugget", "Liquid Glass"),
            10: QtCore.QCoreApplication.translate("Nugget", "Icon Themes"),
            11: QCoreApplication.translate("Nugget", "Passcode Themes"),
            12: QCoreApplication.translate("Nugget", "MobileGestalt"),
            13: QCoreApplication.translate("Nugget", "Backup"),
            14: QCoreApplication.translate("Nugget", "Themes"),
            15: QCoreApplication.translate("Nugget", "App Data"),
        }
        self._nav_right_actions = {
            2: ("+ Add Tendies", self.ios_posterboard.show_add_tendies_dialog),
            10: (QtCore.QCoreApplication.translate("Nugget", "+ Add Icon"),
                 self.ios_iconthemes.show_add_icon_dialog),
            11: (QCoreApplication.translate("Nugget", "+ Theme"),
                 self.ios_passthemes.choose_theme_dialog),
        }
        self.ios_pages.currentChanged.connect(self._update_shared_nav)

        ios_root = QtWidgets.QWidget(self)
        ios_root_layout = QtWidgets.QVBoxLayout(ios_root)
        ios_root_layout.setContentsMargins(0, 0, 0, 0)
        ios_root_layout.setSpacing(0)
        ios_root_layout.addWidget(self.ios_nav)
        ios_root_layout.addWidget(self.ios_pages)

        # Unified shell: the classic GoldenNugget UI is gone. The stack holds
        # only the iOS-style pages (index 0). The generated Ui_Nugget object
        # still exists for the hidden device-bar widgets that background flows
        # (device refresh, picker signals) reference.
        self.ui.centralwidget.setParent(None)
        self.ui.homePage.setParent(None)
        self.ui.sidebar.setParent(None)
        self.ui.daemonsPage.setParent(None)
        # the top device bar (phone icon + picker) comes back too
        self.ui.deviceBar.setParent(None)
        self.content_stack = QtWidgets.QStackedWidget(self)
        self.content_stack.addWidget(ios_root)           # 0 = iOS pages
        self.content_stack.setStyleSheet("background: transparent;")
        shell = QtWidgets.QWidget(self)
        shell.setProperty("cls", "central")  # shell background comes from SkyBackground
        # Overlay grid: animated sky background behind the content.
        overlay = QtWidgets.QGridLayout(shell)
        overlay.setContentsMargins(0, 0, 0, 0)
        overlay.setSpacing(0)
        from src.gui.ios.sky_bg import SkyBackground
        self._sky_bg = SkyBackground(shell)
        self._sky_bg.start()
        overlay.addWidget(self._sky_bg, 0, 0)
        content = QtWidgets.QWidget(shell)
        content.setStyleSheet("background: transparent; border: none;")
        overlay.addWidget(content, 0, 0)
        content.raise_()  # keep content above the sky background
        self.shell_layout = QtWidgets.QVBoxLayout(content)
        self.shell_layout.setContentsMargins(0, 0, 0, 0)
        self.shell_layout.setSpacing(0)
        self.shell_layout.addWidget(self.ui.deviceBar)
        self.body_row = QtWidgets.QHBoxLayout()
        self.body_row.setContentsMargins(0, 0, 0, 0)
        self.body_row.setSpacing(0)
        # WorkSlop sidebar: white navigation rail. The generated-UI
        # sidebar is parked hidden — old flows still touch its buttons, but
        # navigation now goes through the new rail.
        from src.gui.ios.sidebar import WorkSlopSidebar
        self.ui.sidebar.hide()
        self.workslop_sidebar = WorkSlopSidebar(self)
        self.workslop_sidebar.menu_selected.connect(self._on_workslop_menu)
        self.body_row.addWidget(self.workslop_sidebar)
        self.body_row.addWidget(self.content_stack, 1)
        self._style_device_pill()
        self.shell_layout.addLayout(self.body_row)
        self.setCentralWidget(shell)

        # WorkSlop Desktop branding (the generated .ui still says GoldenNugget;
        # overriding here keeps mainwindow_ui.py untouched).
        self.setWindowTitle("WorkSlop Desktop")

        # Sky theme: light-blue shell with the animated SkyBackground canvas.
        # The CobaltBackdrop is retired — keeping it would repaint bubbles
        # every frame for no visible effect on an opaque background.
        self._backdrop = None

        self.apply_theme(self.theme_manager.current_theme)

        # Back navigation: ESC key and mouse back button go to the home page
        QtWidgets.QApplication.instance().installEventFilter(self)

        # Update the app version/build number label
        self.updateAppVersionLabel()
        self.pages[Page.Home].load()
        
        ## DEVICE BAR
        self.refresh_devices()

        self.ui.refreshBtn.clicked.connect(self.refresh_devices)
        self.ui.devicePicker.currentIndexChanged.connect(self.change_selected_device)

        ## SIDE BAR ACTIONS
        self.ui.homePageBtn.clicked.connect(self.on_homePageBtn_clicked)
        self.ui.statusBarPageBtn.clicked.connect(self.on_statusBarPageBtn_clicked)
        self.ui.springboardOptionsPageBtn.clicked.connect(self.on_springboardOptionsPageBtn_clicked)
        self.ui.internalOptionsPageBtn.clicked.connect(self.on_internalOptionsPageBtn_clicked)
        self.ui.liquidGlassPageBtn.clicked.connect(self.on_liquidGlassPageBtn_clicked)
        self.ui.daemonsPageBtn.clicked.connect(self.on_daemonsPageBtn_clicked)
        self.ui.gestaltPageBtn.clicked.connect(self.on_mobileGestaltPageBtn_clicked)
        self.ui.iconThemesPageBtn.clicked.connect(self.on_iconThemesPageBtn_clicked)
        self.ui.posterboardPageBtn.clicked.connect(self.on_posterboardPageBtn_clicked)
        self.ui.applyPageBtn.clicked.connect(self.on_applyPageBtn_clicked)
        self.ui.settingsPageBtn.clicked.connect(self.on_settingsPageBtn_clicked)

        # Apply the initial themed global stylesheet
        self._apply_global_stylesheet()

    def run_first_launch_prompts(self):
        """Present the first-launch dialogs AFTER the window is on screen.

        Running them inside __init__ (before show()) opens them over an
        unmapped parent, which on several platforms renders them transparent
        and stuttering. Called from main_app right after widget.show().
        """
        # First launch: ask user which interface they prefer.
        # TEMP: Classic UI removed — skip the picker, stay on iOS-style.
        if not self.theme_manager.settings.contains("ui/theme"):
            self.theme_manager.save_theme(ThemeManager.IOS)
            self.apply_theme(ThemeManager.IOS)

        # First launch: remind the user to back up the device before tweaking
        # (keeps asking until they confirm a backup was made)
        if not self.settings.value("backup_prompt_done", False, type=bool):
            if self.prompt_first_launch_backup():
                self.settings.setValue("backup_prompt_done", True)
                self._sync_settings()

    # ---- Color theme reactivity ------------------------------------------

    def _apply_global_stylesheet(self):
        """Re-apply the global stylesheet using the current color theme."""
        self.setStyleSheet(t("global"))
        # Also update the QPalette so native widgets pick up the colors
        QtWidgets.QApplication.instance().setPalette(self._color_theme.build_palette())
        # Re-style the ios_pages stack
        self.ios_pages.setStyleSheet(t("page_bg"))
        # Re-style the classic chrome (sidebar icons, device bar, home toolbar)
        self._retheme_classic()

    def _style_device_pill(self):
        """Restyle the top device bar as a clean status pill.

        The picker group moves to the right; the old title text becomes a
        plain expanding spacer.
        """
        c = self._color_theme.colors
        bar = self.ui.deviceBar
        bar.setStyleSheet(f"background-color: {c.bg_primary};")
        layout = self.ui.horizontalLayout_4
        # title spacer first (expanding), device pill last (right-aligned)
        layout.insertWidget(0, self.ui.titleBar)
        self.ui.titleBar.setText("")
        self.ui.titleBar.setStyleSheet("background-color: transparent; border: none;")
        pill = self.ui.horizontalWidget_2
        pill.setStyleSheet(f"""
            QWidget#horizontalWidget_2 {{
                background-color: {c.bg_secondary};
                border: 1px solid {c.border};
                border-radius: 19px;
            }}
        """)
        self.ui.devicePicker.setStyleSheet(f"""
            QComboBox {{
                background-color: transparent;
                border: none;
                color: {c.text_primary};
                font-size: 13px;
                font-weight: 500;
                min-height: 36px;
                padding-left: 10px;
            }}
            QComboBox::drop-down {{ border: none; width: 22px; }}
            QComboBox::down-arrow {{
                image: url(:/icon/caret-down-fill.svg);
                width: 12px; height: 12px; margin-right: 8px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {c.bg_tertiary};
                border: 1px solid {c.border};
                border-radius: 10px;
                color: {c.text_primary};
                selection-background-color: {c.accent};
            }}
        """)
        self.ui.refreshBtn.setStyleSheet(f"""
            QToolButton {{
                background-color: transparent;
                border: none;
                border-radius: 14px;
                color: {c.text_primary};
            }}
            QToolButton:hover {{ background-color: rgba(255, 255, 255, 0.12); }}
        """)
        self.ui.phoneIconBtn.setStyleSheet(
            "background-color: transparent; border: none;")
        # green status dot like the mockup ("iPhone 15 • iOS 26.1 • USB")
        if not hasattr(self, "_device_dot"):
            from PySide6.QtWidgets import QLabel
            self._device_dot = QLabel(pill)
            self._device_dot.setFixedSize(10, 10)
            self._device_dot.setStyleSheet(
                "background-color: #34c759; border-radius: 5px;")
            self.ui.horizontalLayout_19.insertWidget(0, self._device_dot)
            self.ui.horizontalLayout_19.setContentsMargins(12, 1, 6, 1)

    def _retheme_classic(self):
        """Re-color the classic shell: chrome icons, device picker, version
        link and the hardcoded-dark credit buttons."""
        c = self._color_theme.colors

        # Recolor white SVG chrome icons to the current text color
        for obj_name, res in _HIDDEN_THEMED_ICONS.items():
            widget = getattr(self.ui, obj_name, None)
            if widget is not None:
                widget.setIcon(theme_icon(res, c.text_primary))

        # Device picker keeps its Designer stylesheet untouched (classic look).

        # Version link inherits white from the .ui — restyle to text_secondary
        self.ui.phoneNameLbl.setStyleSheet(f"color: {c.text_primary};")
        self.ui.phoneVersionLbl.setText(
            f'<a style="text-decoration:none; color:{c.text_secondary}" href="#">Version</a>')

        # Always-visible shell chrome: the sidebar and device bar are shown on
        # every page/tab, so their text color must be themed explicitly
        # (otherwise it falls back to whatever the .ui bundled).
        chrome = f"""
            QToolButton {{
                color: {c.text_primary};
                background: transparent;
            }}
            QToolButton:hover {{
                color: {c.text_primary};
                background-color: {c.surface_hover};
            }}
            QLabel {{ color: {c.text_primary}; }}
        """
        self.ui.sidebar.setStyleSheet(chrome)

        # Credit buttons hardcode #3b3b3b borders in the generated .ui
        bordered_style = themed_stylesheet("classic_bordered_btn")
        for obj_name in _HIDDEN_BORDERED_BTNS:
            widget = getattr(self.ui, obj_name, None)
            if widget is not None:
                widget.setStyleSheet(bordered_style)

    def _on_color_theme_changed(self):
        """Called when the color theme (dark/light or accent) changes."""
        self._apply_global_stylesheet()
        # Keep the bubble backdrop in sync with the palette.
        try:
            _c = self._color_theme.colors
            self._backdrop.set_colors(_c.bubble, "rgba(180, 205, 255, 40)")
        except Exception:
            pass
        # Keep the device pill themed too.
        try:
            self._style_device_pill()
        except Exception:
            pass
        # Force re-render of all iOS page stylesheets by re-applying them
        for i in range(self.ios_pages.count()):
            page = self.ios_pages.widget(i)
            if page and hasattr(page, '_retheme'):
                page._retheme()

    def closeEvent(self, event):
        """Guard window close so device threads never get destroyed mid-run.

        Destroying a QThread object while its native thread is still running
        is what produces the "QThread: Destroyed while thread '' is still
        running" crash — and for a restore/apply it can cut the device
        operation short right in the middle of a Manifest.db write, leaving
        the backup corrupted (the reported MBErrorDomain/205 fallout).
        """
        terminating = []
        if getattr(self, "apply_in_progress", False):
            terminating.append("apply/reset")
        if getattr(self, "_cache_restore_in_progress", False):
            terminating.append("data restore")
        pt_worker = getattr(getattr(self, "ios_passthemes", None), "_worker", None)
        if _still_running(pt_worker):
            terminating.append("passcode theme write")
        pairing_worker = getattr(
            getattr(self, "ios_settings", None), "_reset_pairing_thread", None)
        if _still_running(pairing_worker):
            terminating.append("pairing reset")
        if terminating:
            reply = QtWidgets.QMessageBox.question(
                self,
                QCoreApplication.tr("Background device operation"),
                QCoreApplication.translate(
                    "Nugget",
                    "A device %1 is running. Closing now can interrupt it "
                    "mid-write and leave the protective backup corrupted.\n\n"
                    "Close anyway?").replace(
                        "%1", " and ".join(terminating)),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
                QtWidgets.QMessageBox.StandardButton.Cancel,
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            # User insisted: let the operation wind down on its own so the
            # thread is not destroyed mid-run. Device loops all have bounded
            # timeouts, so this terminates.
            for worker in (
                getattr(self, "worker_thread", None),
                getattr(self, "_cache_restore_thread", None),
                pairing_worker,
                pt_worker,
            ):
                if _still_running(worker):
                    try:
                        worker.wait()
                    except RuntimeError:
                        pass
        scan_worker = getattr(self, "refresh_worker_thread", None)
        if _still_running(scan_worker):
            try:
                scan_worker.wait(8000)
            except RuntimeError:
                pass
        super().closeEvent(event)
