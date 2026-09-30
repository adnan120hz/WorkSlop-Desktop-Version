from PySide6.QtCore import QObject, Signal, QSettings
from PySide6.QtGui import QColor, QPalette

from src.gui.theme.colors import ThemeColors, DARK, ACCENT_PRESETS
from src.controllers.settings import migrate_legacy_key


def _is_valid_hex(value) -> bool:
    """True for a ``#rrggbb`` string (free-form accent from the color picker)."""
    if not isinstance(value, str):
        return False
    v = value.strip()
    if len(v) != 7 or not v.startswith("#"):
        return False
    try:
        int(v[1:], 16)
    except ValueError:
        return False
    return True


class ColorThemeManager(QObject):
    """Manages the app's color theme (dark + accent).

    Singleton accessed via ``ColorThemeManager.instance()``.
    Emits ``theme_changed`` whenever the palette or accent changes so
    connected widgets can re-render their stylesheets.
    """

    theme_changed = Signal()

    _inst = None

    def __init__(self, parent=None):
        super().__init__(parent)
        # One-time: carry over the accent saved by GoldenNugget/Nugget builds.
        migrate_legacy_key("accent_color")
        self._settings = QSettings("WorkSlop", "WorkSlop")
        saved = self._settings.value("accent_color", "blue")
        if saved in ACCENT_PRESETS:
            self._accent_name = saved
            self._custom_hex = None
        elif _is_valid_hex(saved):
            self._accent_name = "custom"
            self._custom_hex = saved.strip().lower()
        else:
            self._accent_name = "blue"
            self._custom_hex = None
        self._colors = self._build_colors()

    @classmethod
    def instance(cls) -> "ColorThemeManager":
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst

    # ---- current palette ------------------------------------------------

    @property
    def colors(self) -> ThemeColors:
        return self._colors

    @property
    def mode(self) -> str:
        return "dark"

    @property
    def is_dark(self) -> bool:
        return True

    def c(self, slot: str) -> str:
        """Shortcut: return the hex value for *slot* from the active palette."""
        return getattr(self._colors, slot)

    # ---- switching -------------------------------------------------------

    def set_accent(self, name: str):
        if name not in ACCENT_PRESETS:
            return
        if name == self._accent_name:
            return
        self._accent_name = name
        self._custom_hex = None
        self._settings.setValue("accent_color", name)
        self._colors = self._build_colors()
        self.theme_changed.emit()

    def set_accent_hex(self, hex_color: str):
        """Free-form accent color from the color picker (``#rrggbb``).

        Stored in the same ``accent_color`` QSettings key as presets, so the
        save mechanism is unchanged.
        """
        if not _is_valid_hex(hex_color):
            return
        hex_color = hex_color.strip().lower()
        if self._accent_name == "custom" and self._custom_hex == hex_color:
            return
        self._accent_name = "custom"
        self._custom_hex = hex_color
        self._settings.setValue("accent_color", hex_color)
        self._colors = self._build_colors()
        self.theme_changed.emit()

    # ---- QPalette for Fusion style ---------------------------------------

    def build_palette(self) -> QPalette:
        pal = QPalette()
        c = self._colors
        # --- Active group (default) ---
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Window, QColor(c.bg_primary))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText, QColor(c.text_primary))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Base, QColor(c.bg_input))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.AlternateBase, QColor(c.bg_tertiary))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ToolTipBase, QColor(c.bg_elevated))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ToolTipText, QColor(c.text_primary))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Text, QColor(c.text_primary))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Button, QColor(c.bg_secondary))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText, QColor(c.text_primary))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.BrightText, QColor(c.error))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Link, QColor(c.accent))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.LinkVisited, QColor(c.accent_pressed))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, QColor(c.accent))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText, QColor(c.text_inverse))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.PlaceholderText, QColor(c.text_secondary))
        # 3-D bevel / shading roles needed by Fusion on Windows
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Light, QColor(c.bg_elevated))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Midlight, QColor(c.border))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Dark, QColor(c.border))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Mid, QColor(c.border))
        pal.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Shadow, QColor("#000000"))
        # --- Inactive group ---
        pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Window, QColor(c.bg_primary))
        pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.WindowText, QColor(c.text_primary))
        pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Base, QColor(c.bg_input))
        pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.AlternateBase, QColor(c.bg_tertiary))
        pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text, QColor(c.text_primary))
        pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Button, QColor(c.bg_secondary))
        pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ButtonText, QColor(c.text_primary))
        pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor(c.accent))
        pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, QColor(c.text_inverse))
        pal.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.PlaceholderText, QColor(c.text_secondary))
        # --- Disabled group ---
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window, QColor(c.bg_primary))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(c.text_disabled))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(c.bg_input))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(c.text_disabled))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(c.bg_secondary))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(c.text_disabled))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.BrightText, QColor(c.error))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(c.border))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor(c.text_disabled))
        pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.PlaceholderText, QColor(c.text_disabled))
        return pal

    # ---- helpers ---------------------------------------------------------

    def _build_colors(self) -> ThemeColors:
        if self._accent_name == "custom" and self._custom_hex:
            accent = self._custom_hex
            hover = QColor(accent).darker(115).name()
            pressed = QColor(accent).darker(130).name()
        else:
            accent, hover, pressed = ACCENT_PRESETS[self._accent_name]
        return DARK.with_accent(accent, hover, pressed)

    def accent_hex(self) -> str:
        """Return the ``#rrggbb`` string for the current accent."""
        if self._accent_name == "custom" and self._custom_hex:
            return self._custom_hex
        accent, _, _ = ACCENT_PRESETS[self._accent_name]
        return accent

    def accent_rgb(self) -> tuple:
        q = QColor(self.accent_hex())
        return (q.red(), q.green(), q.blue())
