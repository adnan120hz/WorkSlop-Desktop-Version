from ..page import Page
from src.qt.mainwindow_ui import Ui_Nugget
from src.gui.ios.daemons import IOSDaemonsContent
from src.gui.theme import ColorThemeManager
from src.gui.theme.colors import NUGGET_DARK


class DaemonsPage(Page):
    def __init__(self, ui: Ui_Nugget, window):
        super().__init__()
        self.ui = ui
        self.window = window
        self._content = None
        self._full_nugget = False

    def load_page(self):
        if self._content is not None:
            return

        c = NUGGET_DARK if self._full_nugget else \
            ColorThemeManager.instance().colors
        self.ui.daemonsScrollArea.setStyleSheet(
            f"background-color: {c.bg_primary}; border: none;")
        self._content = IOSDaemonsContent(
            self.window, self.ui.daemonsScrollContent)
        self.ui.daemonsScrollLayout.addWidget(self._content)
        self._content.set_full_nugget(self._full_nugget)

    def set_full_nugget(self, enabled: bool):
        """Full Nugget (third interface): the classic Daemons page takes
        the Nugget-original dark palette; the WorkSlop-icon flavor and
        the main UI keep the themed look. Colors only."""
        self._full_nugget = bool(enabled)
        c = NUGGET_DARK if enabled else \
            ColorThemeManager.instance().colors
        self.ui.daemonsScrollArea.setStyleSheet(
            f"background-color: {c.bg_primary}; border: none;")
        if self._content is not None:
            self._content.set_full_nugget(enabled)

    def refresh(self):
        if self._content is not None:
            self._content.refresh_from_tweaks()
