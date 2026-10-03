"""WorkSlop Desktop UI mode: dual interface (user order 2026-10-03).

Two shells share one window and one page stack:

* ``IOS`` (1) — the WorkSlop v4 interface: Sky shell with the light
  sidebar rail and the iOS-style pages. This is the main UI and the
  default for fresh installs.
* ``CLASSIC`` (0) — the Nugget interface: the classic desktop shell
  (device bar + generated sidebar + classic Home/Daemons pages, with the
  iOS-style pages hosted as actions), its icons swapped to the WorkSlop
  icon set.

The choice persists in ``ui/theme`` ("ios" / "classic"); the first-launch
InterfacePickerDialog and the Settings interface switch both write it.
This restores the mechanism that commit 445efe3 retired ("temporarily
disable classic UI"), with the WorkSlop shell as the default side.
"""
from PySide6.QtCore import QSettings


class ThemeManager:
    CLASSIC = 0
    IOS = 1

    def __init__(self, parent):
        self.parent = parent
        self.settings = QSettings("WorkSlop", "WorkSlop")
        self.current_theme = self.load_theme()

    def load_theme(self) -> int:
        val = self.settings.value("ui/theme", "ios")
        return self.CLASSIC if val == "classic" else self.IOS

    def save_theme(self, theme: int):
        val = "ios" if theme == self.IOS else "classic"
        self.settings.setValue("ui/theme", val)
        self.current_theme = theme

    def switch_to(self, theme: int):
        # Container switching is handled by MainWindow.apply_theme().
        self.save_theme(theme)
