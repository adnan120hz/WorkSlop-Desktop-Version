"""WorkSlop Desktop UI mode. The classic GoldenNugget shell is removed;
the app always runs the Sky-style iOS interface."""
from PySide6.QtCore import QSettings


class ThemeManager:
    IOS = 1

    def __init__(self, parent):
        self.parent = parent
        self.settings = QSettings("WorkSlop", "WorkSlop")
        self.current_theme = self.IOS

    def load_theme(self) -> int:
        return self.IOS

    def save_theme(self, theme: int):
        self.settings.setValue("ui/theme", "ios")
        self.current_theme = self.IOS

    def switch_to(self, theme: int):
        self.save_theme(theme)
