from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ThemeColors:
    """All named color slots used across the application."""

    # Surfaces
    bg_primary: str
    bg_secondary: str
    bg_tertiary: str
    bg_input: str
    bg_elevated: str

    # Text
    text_primary: str
    text_secondary: str
    text_disabled: str
    text_inverse: str

    # Accent
    accent: str
    accent_hover: str
    accent_pressed: str

    # Semantic
    success: str
    error: str
    error_hover: str
    error_pressed: str
    warning: str

    # Borders / dividers
    border: str
    divider: str

    # Interactive
    scrollbar: str
    scrollbar_pressed: str
    selection: str

    # Special
    card_border: str
    surface_hover: str
    danger_text: str

    # Cobalt Flow (WorkSlop Desktop) — gradient + glass slots. Defaults keep
    # every existing ThemeColors(...) construction working; the DARK palette
    # below overrides them with the real values.
    bg_gradient_start: str = "#0C1C4E"
    bg_gradient_end: str = "#050A20"
    glass_bg: str = "rgba(35, 64, 150, 110)"
    glass_border: str = "rgba(150, 180, 255, 40)"
    bubble: str = "rgba(140, 175, 255, 26)"

    # Terminal theme (WorkSlop Desktop): white navigation menu on a black
    # terminal body. Defaults keep older constructions working.
    menu_bg: str = "#FFFFFF"
    menu_text: str = "#0A0A0A"
    menu_dim: str = "#6B6B6B"
    menu_active_bg: str = "#0A0A0A"
    menu_active_text: str = "#FFFFFF"
    term_green: str = "#00E676"
    term_green_dim: str = "#00884a"

    def with_accent(self, accent: str, hover: str, pressed: str) -> "ThemeColors":
        return replace(self, accent=accent, accent_hover=hover, accent_pressed=pressed)


# ---------------------------------------------------------------------------
# Terminal palette (WorkSlop Desktop): soft-black body (pure black + pure
# white at full brightness strains the eyes, so the background is lifted
# to a very dark blue-gray and text to an off-white), white navigation
# menu, terminal-green accents, monospace type. Flat and solid — no
# gradients, no blur, no translucency on text surfaces.
# ---------------------------------------------------------------------------
DARK = ThemeColors(
    bg_primary="#0B0E12",
    bg_secondary="#10141A",
    bg_tertiary="#171C23",
    bg_input="#10141A",
    bg_elevated="#151A21",

    text_primary="#E8EAED",
    text_secondary="#9BA3AB",
    text_disabled="#646A72",
    text_inverse="#0B0E12",

    accent="#00C853",
    accent_hover="#3BE08A",
    accent_pressed="#00963F",

    success="#00C853",
    error="#FF6B6B",
    error_hover="#FF8585",
    error_pressed="#D33A3A",
    warning="#FFD740",

    border="#2B3138",
    divider="#2B3138",

    scrollbar="#343B43",
    scrollbar_pressed="#41484F",
    selection="#00C853",

    card_border="#2B3138",
    surface_hover="#1D232B",
    danger_text="#FF6B6B",

    bg_gradient_start="#0B0E12",
    bg_gradient_end="#0B0E12",
    glass_bg="#11161C",
    glass_border="#2B3138",
    bubble="rgba(0, 0, 0, 0)",

    menu_bg="#FFFFFF",
    menu_text="#0A0A0A",
    menu_dim="#6B6B6B",
    menu_active_bg="#10141A",
    menu_active_text="#FFFFFF",
    term_green="#00C853",
    term_green_dim="#007A43",
)


# ---------------------------------------------------------------------------
# Accent presets: (normal, hover, pressed)
# ---------------------------------------------------------------------------
ACCENT_PRESETS = {
    "blue":     ("#007AFF", "#0066CC", "#0055AA"),
    "purple":   ("#AF52DE", "#9B47C4", "#893DAB"),
    "pink":     ("#FF2D55", "#E6284D", "#CC2244"),
    "red":      ("#FF3B30", "#E6352B", "#CC2F26"),
    "orange":   ("#FF9500", "#E68600", "#CC7700"),
    "yellow":   ("#FFCC00", "#E6B800", "#CCA300"),
    "green":    ("#34C759", "#2EAF4E", "#289944"),
    "teal":     ("#5AC8FA", "#50B4E6", "#46A0D2"),
}
