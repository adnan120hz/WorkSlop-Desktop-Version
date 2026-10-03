"""WorkSlop Desktop UI mode: three interfaces (user order 2026-10-03).

Three shells share one window and one page stack:

* ``IOS`` (1) — the WorkSlop v4 interface: Sky shell with the light
  sidebar rail and the iOS-style pages. This is the main UI and the
  default for fresh installs. (Internal name kept from the v4-era
  dual-UI code.)
* ``CLASSIC`` (0) — the Nugget interface with WorkSlop icons: the
  classic desktop shell (device bar + generated sidebar + classic
  Home/Daemons pages, with the iOS-style pages hosted as actions), its
  icons swapped to the WorkSlop icon set (ws-*.svg).
* ``FULL_NUGGET`` (2) — the Full Nugget interface: the same classic
  shell, but with the original Nugget icons and chrome styling
  untouched; only the app name and app icon are WorkSlop.

The choice persists in ``ui/theme`` ("ios" / "classic" / "full_nugget");
the first-launch InterfacePickerDialog and the Settings interface
picker both write it. Values stored by older builds keep their meaning
("classic" still lands on the WorkSlop-icon Nugget UI), and an unknown
value falls back to the WorkSlop UI, so no saved setting can trap the
user in a shell with no way back.
"""
from PySide6.QtCore import QSettings


class ThemeManager:
    CLASSIC = 0
    IOS = 1
    FULL_NUGGET = 2

    _TO_VALUE = {CLASSIC: "classic", IOS: "ios", FULL_NUGGET: "full_nugget"}
    _FROM_VALUE = {"classic": CLASSIC, "full_nugget": FULL_NUGGET}

    def __init__(self, parent):
        self.parent = parent
        self.settings = QSettings("WorkSlop", "WorkSlop")
        self.current_theme = self.load_theme()

    @staticmethod
    def is_classic(theme: int) -> bool:
        """True for both Nugget shells (they differ only in flavor)."""
        return theme in (ThemeManager.CLASSIC, ThemeManager.FULL_NUGGET)

    def load_theme(self) -> int:
        val = self.settings.value("ui/theme", "ios")
        return self._FROM_VALUE.get(val, self.IOS)

    def save_theme(self, theme: int):
        self.settings.setValue(
            "ui/theme", self._TO_VALUE.get(theme, "ios"))
        self.current_theme = theme

    def switch_to(self, theme: int):
        # Container switching is handled by MainWindow.apply_theme().
        self.save_theme(theme)
