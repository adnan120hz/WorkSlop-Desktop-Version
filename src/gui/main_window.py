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
from src.gui.ios.liquid_glass_disable import IOSLiquidGlassDisablePage
from src.gui.ios.icon_themes import IOSIconThemesPage
from src.gui.ios.passcode_theme import IOSPasscodeThemePage
from src.tweaks.registry import Section

from src.gui.theme import ColorThemeManager, t, theme_icon, themed_stylesheet

from src.gui.main_window_mixins import (
    ApplyMixin,
    DeviceBarMixin,
    NavigationMixin,
    SettingsMixin,
    device_operations_running,
)

# Classic (Nugget UI) chrome — device bar, sidebar, home toolbar — uses
# the WorkSlop icon set (ws-*.svg, Wave 11, user order 2026-10-03: the
# second UI is the Nugget shell with its icons renamed to the WorkSlop
# set); they are recolored on every theme change. The credit/social
# buttons keep their brand glyphs (a GitHub/Discord mark cannot be
# renamed to a WorkSlop line icon without lying about where they go).
_HIDDEN_THEMED_ICONS = {
    "phoneIconBtn": ":/icon/ws-device.svg",
    "refreshBtn": ":/icon/ws-refresh.svg",
    "homePageBtn": ":/icon/ws-device.svg",
    "gestaltPageBtn": ":/icon/ws-chip.svg",
    "euEnablerPageBtn": ":/icon/ws-flash.svg",
    "statusBarPageBtn": ":/icon/ws-signal.svg",
    "passcodePageBtn": ":/icon/ws-toolbox.svg",
    "springboardOptionsPageBtn": ":/icon/ws-apps.svg",
    "internalOptionsPageBtn": ":/icon/ws-sliders.svg",
    "liquidGlassPageBtn": ":/icon/ws-glass.svg",
    "daemonsPageBtn": ":/icon/ws-sliders.svg",
    "iconThemesPageBtn": ":/icon/ws-wallpaper.svg",
    "applyPageBtn": ":/icon/ws-backup.svg",
    "backupPageBtn": ":/icon/ws-backup.svg",
    "posterboardPageBtn": ":/icon/ws-poster.svg",
    "settingsPageBtn": ":/icon/ws-gear.svg",
    "mainDevBtn": ":/icon/github.svg",
    "discordBtn": ":/icon/discord.svg",
    "starOnGithubBtn": ":/icon/star.svg",
    "leminGithubBtn": ":/icon/github.svg",
    "leminTwitterBtn": ":/icon/twitter.svg",
    "leminKoFiBtn": ":/icon/currency-dollar.svg",
}

# The original Nugget icon for every classic-shell button, exactly as
# the generated .ui assigns them (src/qt/mainwindow_ui.py). The Full
# Nugget interface (third UI) restores these untouched; the second UI
# replaces them with the WorkSlop set above. Only the app name and app
# icon differ from upstream Nugget in Full Nugget mode.
_CLASSIC_ORIGINAL_ICONS = {
    "phoneIconBtn": ":/icon/phone.svg",
    "refreshBtn": ":/icon/arrow-clockwise.svg",
    "homePageBtn": ":/icon/house.svg",
    "posterboardPageBtn": ":/icon/wallpaper.svg",
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
    "backupPageBtn": ":/icon/shippingbox.svg",
    "settingsPageBtn": ":/icon/gear.svg",
    "mainDevBtn": ":/icon/github.svg",
    "discordBtn": ":/icon/discord.svg",
    "starOnGithubBtn": ":/icon/star.svg",
    "leminGithubBtn": ":/icon/github.svg",
    "leminTwitterBtn": ":/icon/twitter.svg",
    "leminKoFiBtn": ":/icon/currency-dollar.svg",
}
_HIDDEN_BORDERED_BTNS = [
    "helpFromBtn", "posterRestoreBtn", "snoolieBtn", "disfordottieBtn",
    "mikasaBtn", "wind0ws11AeroBtn", "translatorsBtn", "libiBtn",
    "duyBtn", "jjtechBtn", "qtBtn",
]

def _ios_page_property(attr):
    """Lazy iOS page attribute: the page builds on first access.

    Pages are constructed by ``MainWindow._ensure_ios_page``; until then
    only a plain placeholder sits in the stack at that index (indices
    never shift). Every existing ``self.ios_*`` reference keeps working —
    it just pays the page's build cost on first use instead of eagerly
    building all 17 pages (and their ~3.4k widgets) at startup.
    """
    def getter(self):
        return self._ensure_ios_page(self._ios_page_index[attr])

    def setter(self, value):
        self._ios_page_objs[attr] = value

    return property(getter, setter)


class MainWindow(QtWidgets.QMainWindow, DeviceBarMixin, SettingsMixin,
                 NavigationMixin, ApplyMixin):
    # Lazy iOS pages (built on first access/navigation; see above).
    ios_home = _ios_page_property("ios_home")
    ios_tweaks = _ios_page_property("ios_tweaks")
    ios_posterboard = _ios_page_property("ios_posterboard")
    ios_daemons = _ios_page_property("ios_daemons")
    ios_settings = _ios_page_property("ios_settings")
    ios_statusbar = _ios_page_property("ios_statusbar")
    ios_apply = _ios_page_property("ios_apply")
    ios_springboard = _ios_page_property("ios_springboard")
    ios_internal = _ios_page_property("ios_internal")
    ios_liquidglass = _ios_page_property("ios_liquidglass")
    ios_iconthemes = _ios_page_property("ios_iconthemes")
    ios_passthemes = _ios_page_property("ios_passthemes")
    ios_gestalt = _ios_page_property("ios_gestalt")
    ios_backup = _ios_page_property("ios_backup")
    ios_themes_hub = _ios_page_property("ios_themes_hub")
    ios_appdata = _ios_page_property("ios_appdata")
    ios_lgd = _ios_page_property("ios_lgd")

    def __init__(self, device_manager: "DeviceManager", translator: Translator):
        super(MainWindow, self).__init__()
        self.device_manager = device_manager
        self.translator = translator
        # Lazy-page bookkeeping (see _ios_page_property): attr name ->
        # stack index, built pages, and the color-theme generation each
        # built page was last rethemed at. _in_initial_build defers the
        # classic-chrome retheme until the end of __init__.
        self._ios_page_index = {
            "ios_home": 0, "ios_tweaks": 1, "ios_posterboard": 2,
            "ios_daemons": 3, "ios_settings": 4, "ios_statusbar": 5,
            "ios_apply": 6, "ios_springboard": 7, "ios_internal": 8,
            "ios_liquidglass": 9, "ios_iconthemes": 10,
            "ios_passthemes": 11, "ios_gestalt": 12, "ios_backup": 13,
            "ios_themes_hub": 14, "ios_appdata": 15, "ios_lgd": 16,
        }
        self._ios_page_attrs = {idx: attr for attr, idx
                                in self._ios_page_index.items()}
        self._ios_page_objs = {}
        self._ios_page_theme_gen = {}
        self._theme_gen = 0
        self._page_global_qss = {}
        self._in_initial_build = True
        # Device-driven page state collected while a page is still
        # unbuilt; replayed by _ensure_ios_page at construction.
        self._ios_pages_need_rebuild = set()
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
        # Snapshot the classic shell's as-generated stylesheets BEFORE any
        # WorkSlop theming touches them: Full Nugget mode restores these
        # verbatim (only the app name/icon are WorkSlop there).
        self._orig_classic_qss = {
            "sidebar": self.ui.sidebar.styleSheet(),
            "phoneNameLbl": self.ui.phoneNameLbl.styleSheet(),
        }
        for _btn_name in _HIDDEN_BORDERED_BTNS:
            _w = getattr(self.ui, _btn_name, None)
            if _w is not None:
                self._orig_classic_qss[_btn_name] = _w.styleSheet()
        # The generated UI pins setMaximumSize(1000, 600), which on Windows
        # disables the normal maximize button and can keep showFullScreen()
        # from covering the screen. Lift the clamp here (the generated file
        # itself stays untouched, per AGENTS.md) so maximize and F11
        # fullscreen both work.
        self.setMaximumSize(16777215, 16777215)
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

        # Backup entry for the classic sidebar (the two Nugget shells):
        # the generated UI has no Backup button (the main UI's rail has
        # one), so — like the other runtime chrome — it is created here
        # instead of editing the generated file. It sits right above
        # Apply, follows the menu order of the main UI (Backup before
        # Apply), and opens the same Backup & Apply page (iOS page 13).
        # Its icon follows the active flavor through the
        # _HIDDEN_THEMED_ICONS / _CLASSIC_ORIGINAL_ICONS maps above, and
        # the device-refresh flow shows/hides it together with Apply.
        backup_btn = QtWidgets.QToolButton(self.ui.sidebar)
        backup_btn.setObjectName("backupPageBtn")
        backup_btn.setSizePolicy(self.ui.applyPageBtn.sizePolicy())
        backup_btn.setCursor(QtCore.Qt.PointingHandCursor)
        backup_btn.setCheckable(True)
        backup_btn.setAutoExclusive(True)
        backup_btn.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        backup_btn.setProperty("cls", "sidebarBtn")
        backup_btn.setText(QCoreApplication.translate("Nugget", "Backup"))
        self.ui.verticalLayout.insertWidget(
            self.ui.verticalLayout.indexOf(self.ui.applyPageBtn),
            backup_btn)
        backup_btn.hide()
        self.ui.backupPageBtn = backup_btn

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
        # 10 = icon themes, 11 = passcode themes, 12 = mobilegestalt,
        # 13 = backup, 14 = themes hub, 15 = app data,
        # 16 = Liquid Glass Disable (Beta 1). (The iOS 18 Icons table is a
        # section inside Icon Themes, page 10.)
        self.ios_pages = QtWidgets.QStackedWidget(self)
        self.ios_pages.setStyleSheet(t("page_bg"))
        # LAZY PAGES: building all 17 pages up front cost ~1.3s and
        # inflated the widget tree to ~3.4k widgets (which made every
        # global stylesheet polish crawl). Only Home — the landing page —
        # is built now; every other index starts as a plain placeholder
        # and is swapped for the real page by _ensure_ios_page on first
        # navigation/access. Indices never shift.
        self._ios_placeholders = {}
        for _idx in range(17):
            _placeholder = QtWidgets.QWidget(self.ios_pages)
            self._ios_placeholders[_idx] = _placeholder
            self.ios_pages.addWidget(_placeholder)
        self._ensure_ios_page(0)

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
            16: QCoreApplication.translate("Nugget", "Liquid Glass Disable (Beta 1)"),
        }
        # Right-action callables resolve the page lazily (attribute access
        # builds it) so wiring the nav never constructs a page early.
        self._nav_right_actions = {
            2: ("+ Add Tendies",
                lambda: self.ios_posterboard.show_add_tendies_dialog()),
            10: (QtCore.QCoreApplication.translate("Nugget", "+ Add Icon"),
                 lambda: self.ios_iconthemes.show_add_icon_dialog()),
            11: (QCoreApplication.translate("Nugget", "+ Theme"),
                 lambda: self.ios_passthemes.choose_theme_dialog()),
        }
        self.ios_pages.currentChanged.connect(self._update_shared_nav)

        self.ios_root = ios_root = QtWidgets.QWidget(self)
        ios_root_layout = QtWidgets.QVBoxLayout(ios_root)
        ios_root_layout.setContentsMargins(0, 0, 0, 0)
        ios_root_layout.setSpacing(0)
        ios_root_layout.addWidget(self.ios_nav)
        ios_root_layout.addWidget(self.ios_pages)

        # Unified dual shell (Wave 11, user order 2026-10-03). The content
        # stack holds the classic Nugget Home (0), the iOS-style page root
        # (1), and the classic Daemons page (2). Around it, two chromes:
        # the WorkSlop v4 Sky shell (sidebar rail + shared nav header) is
        # the main UI (IOS mode), and the classic Nugget shell (generated
        # sidebar + classic pages, iOS pages hosted as actions) is the
        # second UI (CLASSIC mode). apply_theme() switches between them.
        # The generated Ui_Nugget object still exists for the device-bar
        # widgets that background flows (device refresh, picker signals)
        # reference.
        self.ui.centralwidget.setParent(None)
        self.ui.homePage.setParent(None)
        self.ui.sidebar.setParent(None)
        self.ui.daemonsPage.setParent(None)
        # the top device bar (phone icon + picker) serves both shells
        self.ui.deviceBar.setParent(None)
        self.content_stack = QtWidgets.QStackedWidget(self)
        self.content_stack.addWidget(self.ui.homePage)     # 0 = classic home
        self.content_stack.addWidget(ios_root)             # 1 = iOS pages
        self.content_stack.addWidget(self.ui.daemonsPage)  # 2 = classic daemons
        self.content_stack.setStyleSheet("background: transparent;")
        # Full Nugget (third interface): the original Nugget v7.4.1
        # tweak pages (vendored src/qt/nugget741_ui.py, builders in
        # src/gui/nugget_pages/) live in their own stack here and are
        # built lazily on first use — see NavigationMixin.
        self.nugget_stack = QtWidgets.QStackedWidget(self)
        self.nugget_stack.setStyleSheet("background: transparent;")
        self.content_stack.addWidget(self.nugget_stack)  # 3 = Nugget pages
        self._nugget_ui = None
        self._nugget_ui_host = None
        self._nugget_pages = {}       # key -> page builder
        self._nugget_page_keys = []   # keys in stack order
        shell = QtWidgets.QWidget(self)
        shell.setProperty("cls", "central")
        # Wave 11 shell: animated blue Apple-logo background behind the
        # content. White cards/panels sit above it, like the v4 shell.
        from src.gui.ios.sky_bg import SkyBackground
        self._sky_bg = SkyBackground(shell)
        self._sky_bg.start()  # v4: drifting logos animate from window start
        self._shell = shell
        content = QtWidgets.QWidget(shell)
        content.setStyleSheet("background: transparent; border: none;")
        shell_layout = QtWidgets.QStackedLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.setStackingMode(QtWidgets.QStackedLayout.StackAll)
        shell_layout.addWidget(self._sky_bg)
        shell_layout.addWidget(content)
        self._sky_bg.lower()
        self.shell_layout = QtWidgets.QVBoxLayout(content)
        self.shell_layout.setContentsMargins(0, 0, 0, 0)
        self.shell_layout.setSpacing(0)
        self.shell_layout.addWidget(self.ui.deviceBar)
        self.body_row = QtWidgets.QHBoxLayout()
        self.body_row.setContentsMargins(0, 0, 0, 0)
        self.body_row.setSpacing(0)
        # Classic (Nugget) sidebar: visible in CLASSIC mode only. Its page
        # buttons are shown/hidden by the device-refresh flow and HotLoad
        # gating exactly as in the v4-era dual shell.
        self.body_row.addWidget(self.ui.sidebar)
        # WorkSlop v4 sidebar rail: visible in IOS mode (the main UI).
        from src.gui.ios.sidebar import WorkSlopSidebar
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

        # Animated blue Apple-logo background is instantiated above as
        # the shell underlay (self._sky_bg).
        self._backdrop = self._sky_bg

        self.apply_theme(self.theme_manager.current_theme)

        # Back navigation: ESC key and mouse back button go to the home page
        QtWidgets.QApplication.instance().installEventFilter(self)
        # F11/ESC fullscreen via real window shortcuts (the app-wide event
        # filter alone does not reliably deliver F11 on Windows).
        self._install_fullscreen_shortcuts()

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
        self.ui.backupPageBtn.clicked.connect(self.on_backupPageBtn_clicked)
        self.ui.settingsPageBtn.clicked.connect(self.on_settingsPageBtn_clicked)

        # Apply the initial themed global stylesheet (once, now that the
        # whole tree exists — see _apply_global_stylesheet). Construction
        # is over: deferred chrome theming is allowed from here on.
        self._in_initial_build = False
        self._apply_global_stylesheet()

    # ---- Lazy iOS pages ---------------------------------------------------

    def _build_ios_page(self, index: int):
        """Construct the real page for a stack index (factories)."""
        if index == 0:
            return IOSHomePage(self)
        if index == 1:
            return IOSTweaksPage(self)
        if index == 2:
            return IOSPosterboardPage(self)
        if index == 3:
            return IOSDaemonsPage(self)
        if index == 4:
            return IOSSettingsPage(self)
        if index == 5:
            return IOSStatusBarPage(self)
        if index == 6:
            return IOSApplyPage(self)
        if index == 7:
            return IOSSectionPage(self, Section.SPRINGBOARD)
        if index == 8:
            return IOSSectionPage(self, Section.INTERNAL)
        if index == 9:
            return IOSSectionPage(self, Section.LIQUID_GLASS)
        if index == 10:
            return IOSIconThemesPage(self)
        if index == 11:
            return IOSPasscodeThemePage(self)
        if index == 12:
            return IOSMobileGestaltPage(self)
        if index == 13:
            from src.gui.ios.backup import IOSBackupPage
            return IOSBackupPage(self)
        if index == 14:
            from src.gui.ios.themes_hub import IOSThemesHubPage
            return IOSThemesHubPage(self)
        if index == 15:
            from src.gui.ios.appdata import IOSAppDataPage
            return IOSAppDataPage(self)
        if index == 16:
            return IOSLiquidGlassDisablePage(self)
        raise IndexError(f"unknown iOS page index {index}")

    def _ensure_ios_page(self, index: int):
        """Return the real page for *index*, building it on first use.

        The placeholder in the stack is swapped for the built page at the
        same index. Shell-flavour state that apply_theme pushes onto
        already-built pages (Full Nugget flag, Nugget Liquid Glass
        visibility) is applied here so a lazily-built page lands in the
        same state an eagerly-built one would have had.
        """
        attr = self._ios_page_attrs[index]
        page = self._ios_page_objs.get(attr)
        if page is not None:
            # The color theme may have changed while this page was
            # hidden; refresh its own styles once (the visible page is
            # rethemed eagerly by _on_color_theme_changed).
            if self._ios_page_theme_gen.get(attr) != self._theme_gen:
                retheme = getattr(page, "_retheme", None)
                if callable(retheme):
                    try:
                        retheme()
                    except Exception:
                        pass
                self._ios_page_theme_gen[attr] = self._theme_gen
                self._prepend_global_qss(page, attr)
            return page
        page = self._build_ios_page(index)
        self._ios_page_objs[attr] = page
        self._ios_page_theme_gen[attr] = self._theme_gen
        placeholder = self._ios_placeholders.pop(index, None)
        if placeholder is not None:
            self.ios_pages.removeWidget(placeholder)
            placeholder.deleteLater()
        self.ios_pages.insertWidget(index, page)
        # Replay device-driven state collected while this page did not
        # exist yet (device selected before first navigation).
        if attr in self._ios_pages_need_rebuild:
            self._ios_pages_need_rebuild.discard(attr)
            rebuild = getattr(page, "rebuild", None)
            if callable(rebuild):
                try:
                    rebuild()
                except Exception:
                    pass
        if attr == "ios_tweaks":
            pending_sf = getattr(
                self, "_pending_force_solarium_visible", None)
            if pending_sf is not None:
                self._pending_force_solarium_visible = None
                try:
                    page.set_force_solarium_fallback_visible(pending_sf)
                except Exception:
                    pass
        if attr == "ios_apply":
            pending_busy = getattr(self, "_pending_apply_busy", None)
            if pending_busy is not None:
                self._pending_apply_busy = None
                try:
                    page.set_busy(pending_busy)
                except Exception:
                    pass
        try:
            if getattr(self, "theme_manager", None) is not None and \
                    self.theme_manager.current_theme == \
                    ThemeManager.FULL_NUGGET and \
                    hasattr(page, "set_full_nugget"):
                page.set_full_nugget(True)
        except Exception:
            pass
        try:
            refresh_lg = getattr(page, "refresh_nugget_lg_visibility", None)
            if callable(refresh_lg):
                refresh_lg()
        except Exception:
            pass
        # Fresh global rules at page level (the window sheet may predate
        # a color change; see _prepend_global_qss).
        try:
            self._prepend_global_qss(page, attr)
        except Exception:
            pass
        return page

    def run_first_launch_prompts(self):
        """Present the first-launch dialogs AFTER the window is on screen.

        Running them inside __init__ (before show()) opens them over an
        unmapped parent, which on several platforms renders them transparent
        and stuttering. Called from main_app right after widget.show().
        """
        # First launch: ask user which interface they prefer (restored
        # Wave 11, user order 2026-10-03 — the v4-era picker retired by
        # 445efe3). WorkSlop (iOS-style) is the main UI, so it is also the
        # fallback when the dialog is dismissed without a choice.
        if not self.theme_manager.settings.contains("ui/theme"):
            from src.gui.interface_picker import InterfacePickerDialog
            dlg = InterfacePickerDialog(self)
            picked = (dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted
                      and dlg.choice)
            self.theme_manager.save_theme({
                "classic": ThemeManager.CLASSIC,
                "full_nugget": ThemeManager.FULL_NUGGET,
            }.get(picked, ThemeManager.IOS))
            self.apply_theme(self.theme_manager.current_theme)

        # First launch: remind the user to back up the device before tweaking
        # (keeps asking until they confirm a backup was made)
        if not self.settings.value("backup_prompt_done", False, type=bool):
            if self.prompt_first_launch_backup():
                self.settings.setValue("backup_prompt_done", True)
                self._sync_settings()

    def on_footer_check_update_clicked(self):
        """Footer "Check Update": run the update checker off the GUI thread
        via the shared UpdateCheckRunner and report on the GUI thread.

        The runner owns the QThread lifecycle (fresh thread per check,
        references dropped on finished, result delivered by queued signal);
        calling this repeatedly — including while a check is running or
        after one finished — cannot touch a deleted C++ QThread again.
        """
        runner = getattr(self, "_footer_update_runner", None)
        if runner is None:
            from src.gui.update_check import UpdateCheckRunner
            runner = UpdateCheckRunner(self)
            runner.result_ready.connect(self._report_footer_update_result)
            self._footer_update_runner = runner
        runner.start()

    def _report_footer_update_result(self, result):
        if result is not None and result.outcome == "update_available":
            from src.gui.dialogs import UpdateAppDialog
            UpdateAppDialog(result, self).exec()
        elif result is not None and result.outcome == "up_to_date":
            QtWidgets.QMessageBox.information(
                self, "Check for Updates", "You are up to date.")
        else:
            QtWidgets.QMessageBox.warning(
                self, "Check for Updates",
                "Couldn't check for updates. Please try again later.")

    def eventFilter(self, obj, event):
        # Delegate explicitly: with QMainWindow first in the MRO, Python
        # attribute lookup would otherwise resolve QObject.eventFilter and
        # the NavigationMixin handler (ESC/back/F11) would never run.
        return NavigationMixin.eventFilter(self, obj, event)

    # ---- Color theme reactivity ------------------------------------------

    def _apply_global_stylesheet(self):
        """Apply the global stylesheet once, with the current color theme.

        Called at the end of __init__ (tree fully built) and nowhere
        else: re-setting a window-level stylesheet re-polishes every
        widget in the tree (~3.4k), so runtime color changes go through
        the narrow path in _on_color_theme_changed instead.
        """
        self.setStyleSheet(t("global"))
        # Also update the QPalette so native widgets pick up the colors
        QtWidgets.QApplication.instance().setPalette(self._color_theme.build_palette())
        # Re-style the ios_pages stack transparently so the animated shell
        # background shows around the white page surfaces.
        self.ios_pages.setStyleSheet("background: transparent;")
        if hasattr(self, "_shell"):
            self._shell.setStyleSheet(
                "background: transparent; border: none;")
        # Re-style the classic chrome (sidebar icons, device bar, home
        # toolbar) — but only when a classic shell is (or will be) the
        # showing one. In iOS mode that chrome is hidden; theming it here
        # would style a shell nobody can see. apply_theme re-themes it
        # the first time the user switches to a classic flavour.
        if getattr(self, "theme_manager", None) is not None and \
                self.theme_manager.current_theme == ThemeManager.IOS:
            pass
        else:
            self._retheme_classic()

    def _style_device_pill(self):
        """Restyle the top device bar as a clean status pill (v4 shell).

        The picker group moves to the right; the old title text becomes a
        plain expanding spacer.

        Full Nugget flavor: the bar melts into upstream's dark window
        (dark #1e1e1e strip, #3b3b3b pill, light text) — it is the only
        interface whose shell is dark; the other two keep the themed
        light pill below untouched.
        """
        # The picker group moves to the right and the old title text is
        # blanked first (every flavor shares this layout fixup).
        bar = self.ui.deviceBar
        layout = self.ui.horizontalLayout_4
        layout.insertWidget(0, self.ui.titleBar)
        self.ui.titleBar.setText("")
        self.ui.titleBar.setStyleSheet(
            "background-color: transparent; border: none;")
        if getattr(self, "theme_manager", None) is not None and \
                self.theme_manager.current_theme == ThemeManager.FULL_NUGGET:
            bar.setStyleSheet("background-color: #1e1e1e;")
            self.ui.horizontalWidget_2.setStyleSheet("""
                QWidget#horizontalWidget_2 {
                    background-color: #3b3b3b;
                    border: 1px solid #4b4b4b;
                    border-radius: 19px;
                }
            """)
            self.ui.devicePicker.setStyleSheet("""
                QComboBox {
                    background-color: transparent;
                    border: none;
                    color: #e8e8e8;
                    font-size: 13px;
                    font-weight: 500;
                    min-height: 36px;
                    padding-left: 10px;
                }
                QComboBox::drop-down { border: none; width: 22px; }
                QComboBox::down-arrow {
                    image: url(:/icon/caret-down-fill.svg);
                    width: 12px; height: 12px; margin-right: 8px;
                }
                QComboBox QAbstractItemView {
                    background-color: #3b3b3b;
                    border: 1px solid #4b4b4b;
                    border-radius: 10px;
                    color: #e8e8e8;
                    selection-background-color: #2860ca;
                }
            """)
            self.ui.refreshBtn.setStyleSheet("""
                QToolButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 14px;
                    color: #FFFFFF;
                }
                QToolButton:hover { background-color: rgba(255, 255, 255, 0.12); }
            """)
            self.ui.phoneIconBtn.setStyleSheet(
                "background-color: transparent; border: none;")
            return
        c = self._color_theme.colors
        bar.setStyleSheet(f"background-color: {c.bg_primary};")
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

    def _retheme_classic(self):
        """Re-color the classic shell: chrome icons, device picker, version
        link and the hardcoded-dark credit buttons.

        Flavor-aware (three-UI, user order 2026-10-03): the second UI
        (Nugget with WorkSlop icons) gets the WorkSlop set + theming
        below; the third UI (Full Nugget) keeps the original Nugget
        icons and chrome, restored by _apply_full_nugget_chrome().
        """
        if getattr(self, "_in_initial_build", False):
            # Deferred during construction: apply_theme runs mid-__init__
            # and would style the classic chrome here, then again from
            # _apply_global_stylesheet at the end of __init__. The end-of
            # -init call (or the first shell switch) does it once.
            return
        if getattr(self, "theme_manager", None) is not None and \
                self.theme_manager.current_theme == ThemeManager.FULL_NUGGET:
            self._apply_full_nugget_chrome()
            return
        # Leaving Full Nugget (or never entering it): the dark shell
        # background must not stick to the WorkSlop / Nugget-WS shells.
        try:
            self._shell.layout().itemAt(1).widget().setStyleSheet(
                "background: transparent;")
        except Exception:
            pass
        for _page_name in ("homePage", "daemonsPage"):
            _page = getattr(self.ui, _page_name, None)
            if _page is not None:
                _page.setStyleSheet("")
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

    def _apply_full_nugget_chrome(self):
        """Full Nugget flavor: original Nugget icons + dark chrome.

        Restores the classic shell's icons (the generated .ui's own set,
        untinted) and re-applies upstream's dark window look — upstream's
        .ui paints white text/icons over a #1e1e1e central background
        with #3b3b3b widgets — so the second UI's WorkSlop icons/colors
        never leak into this flavor. The app name and window icon stay
        WorkSlop (set at startup); everything else is upstream's look.
        The dark shell is cleared again by _retheme_classic() whenever
        another flavor becomes active.
        """
        from PySide6.QtGui import QIcon
        for obj_name, res in _CLASSIC_ORIGINAL_ICONS.items():
            widget = getattr(self.ui, obj_name, None)
            if widget is not None:
                widget.setIcon(QIcon(res))
        # Dark window behind the classic shell (upstream [cls=central]).
        try:
            content = self._shell.layout().itemAt(1).widget()
            content.setStyleSheet("background-color: #1e1e1e;")
        except Exception:
            pass
        self.ui.sidebar.setStyleSheet(
            "#sidebar { background-color: #1e1e1e; }\n"
            "#sidebar QToolButton { color: #FFFFFF;"
            " background: transparent; }\n"
            "#sidebar QToolButton:hover { background-color: #3b3b3b; }\n"
            "#sidebar QToolButton:checked { background-color: #3b3b3b; }\n"
            "#sidebar QLabel { color: #FFFFFF; }")
        # The classic pages' own labels inherit upstream's white text.
        for _page_name in ("homePage", "daemonsPage"):
            _page = getattr(self.ui, _page_name, None)
            if _page is not None:
                _page.setStyleSheet("QLabel { color: #FFFFFF; }")
        orig = getattr(self, "_orig_classic_qss", {})
        if "phoneNameLbl" in orig:
            self.ui.phoneNameLbl.setStyleSheet(
                orig["phoneNameLbl"] + "\ncolor: #FFFFFF;")
        self.ui.phoneVersionLbl.setText("Version")
        for obj_name in _HIDDEN_BORDERED_BTNS:
            widget = getattr(self.ui, obj_name, None)
            if widget is not None and obj_name in orig:
                widget.setStyleSheet(orig[obj_name])

    def _prepend_global_qss(self, widget, key):
        """Layer the fresh global stylesheet under a page's own sheet.

        The window-level stylesheet is applied once at startup and never
        re-set (re-setting it re-polishes the whole widget tree). A page
        that becomes visible after a color change instead gets the
        current global rules prepended to its own stylesheet — same
        selectors, same order as inheritance would give — so bare
        widgets styled only by the global sheet (checkbox indicators,
        checked tool buttons, selections) pick up the new palette while
        the page's own rules keep winning for the page root.
        """
        store = self._page_global_qss
        current = widget.styleSheet()
        prev = store.get(key)
        if prev is not None and current == prev[1]:
            base = prev[0]  # sheet is still (old global + base): reuse base
        else:
            base = current
        css = t("global")
        sheet = css + ("\n" + base if base.strip() else "")
        store[key] = (base, sheet)
        # Audit 91: re-setting an identical sheet re-polishes the page's
        # whole subtree for nothing (the plain re-show path, where the
        # theme has not changed). Skip the call in that case — the page
        # ends up wearing exactly the same sheet.
        if sheet != current:
            widget.setStyleSheet(sheet)

    def _retheme_visible_page(self):
        """Retheme + re-layer the global rules on the visible iOS page.

        Runs deferred from _on_color_theme_changed (see there). Hidden
        pages are untouched: their stale theme generation makes
        _ensure_ios_page retheme them when next shown.
        """
        try:
            index = self.ios_pages.currentIndex()
            attr = self._ios_page_attrs[index]
            page = self._ios_page_objs.get(attr)
            if page is None:
                return
            retheme = getattr(page, "_retheme", None)
            if callable(retheme):
                retheme()
            self._ios_page_theme_gen[attr] = self._theme_gen
            self._prepend_global_qss(page, attr)
        except Exception:
            pass

    def _on_color_theme_changed(self):
        """Called when the color theme (dark/light or accent) changes.

        Narrow by design: re-setting the window stylesheet here used to
        re-polish all ~3.4k widgets and freeze the UI for seconds. Now
        only the palette, the visible chrome and the visible page are
        refreshed; hidden pages/components retheme when next shown
        (theme generation check in _ensure_ios_page, deferred
        _auto_retheme in components).
        """
        self._theme_gen += 1
        # Palette only: native widgets follow it without a re-polish.
        QtWidgets.QApplication.instance().setPalette(
            self._color_theme.build_palette())
        # Repaint the sky backdrop against the current palette (v4
        # SkyBackground paints from the sky tints; a repaint is all it
        # needs — the Wave 10 set_colors API is gone with its backdrop).
        try:
            self._backdrop.update()
        except Exception:
            pass
        # Keep the device pill themed too.
        try:
            self._style_device_pill()
        except Exception:
            pass
        # The visible iOS page refreshes its own styles now; every other
        # built page keeps a stale theme generation and rethemes when it
        # is next shown (see _ensure_ios_page). Deferred past the end of
        # this emission: several pages connect theme_changed straight to
        # their own _retheme, and those slots would otherwise land after
        # this handler and wipe the prepended global rules again.
        QtCore.QTimer.singleShot(0, self._retheme_visible_page)
        # Classic chrome is rethemed only while a classic shell is the
        # showing one; apply_theme re-themes it on the first switch to a
        # classic flavour otherwise.
        try:
            if getattr(self, "theme_manager", None) is not None and \
                    self.theme_manager.current_theme != ThemeManager.IOS:
                self._retheme_classic()
                for _classic_page in (self.ui.homePage, self.ui.daemonsPage):
                    self._prepend_global_qss(
                        _classic_page, _classic_page.objectName())
                if getattr(self, "_nugget_pages", None):
                    self.nugget_stack.setStyleSheet(
                        t("global") + "\nbackground: transparent;")
        except Exception:
            pass

    def closeEvent(self, event):
        """Guard window close so device threads never get destroyed mid-run.

        Destroying a QThread object while its native thread is still running
        is what produces the "QThread: Destroyed while thread '' is still
        running" crash — and for a restore/apply it can cut the device
        operation short right in the middle of a Manifest.db write, leaving
        the backup corrupted (the reported MBErrorDomain/205 fallout).
        """
        # Fix Audit 73: one shared guard list (also used by the Load
        # Preset restart) — it now covers Gestalt apply and full
        # restore too, which closeEvent used to miss.
        terminating = device_operations_running(self)
        page_objs = getattr(self, "_ios_page_objs", None) or {}
        pt_worker = getattr(page_objs.get("ios_passthemes"),
                            "_worker", None)
        pairing_worker = getattr(
            page_objs.get("ios_settings"),
            "_reset_pairing_thread", None)
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
                getattr(self, "_gestalt_apply_thread", None),
                getattr(self, "_full_restore_thread", None),
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
