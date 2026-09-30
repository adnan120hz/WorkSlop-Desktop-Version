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
# Terminal palette (WorkSlop Desktop): pure black body, white navigation
# menu, terminal-green accents, monospace type. Flat and solid — no
# gradients, no blur, no translucency on text surfaces.
# ---------------------------------------------------------------------------
DARK = ThemeColors(
    bg_primary="#000000",
    bg_secondary="#0E0E0E",
    bg_tertiary="#161616",
    bg_input="#0E0E0E",
    bg_elevated="#141414",

    text_primary="#FFFFFF",
    text_secondary="#A6A6A6",
    text_disabled="#5C5C5C",
    text_inverse="#000000",

    accent="#00E676",
    accent_hover="#2BFF8F",
    accent_pressed="#00B35C",

    success="#00E676",
    error="#FF5252",
    error_hover="#FF7373",
    error_pressed="#D33A3A",
    warning="#FFD740",

    border="#262626",
    divider="#262626",

    scrollbar="#2E2E2E",
    scrollbar_pressed="#3D3D3D",
    selection="#00E676",

    card_border="#262626",
    surface_hover="#1C1C1C",
    danger_text="#FF5252",

    bg_gradient_start="#000000",
    bg_gradient_end="#000000",
    glass_bg="#101010",
    glass_border="#262626",
    bubble="rgba(0, 0, 0, 0)",

    menu_bg="#FFFFFF",
    menu_text="#0A0A0A",
    menu_dim="#6B6B6B",
    menu_active_bg="#0A0A0A",
    menu_active_text="#FFFFFF",
    term_green="#00E676",
    term_green_dim="#00884A",
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
