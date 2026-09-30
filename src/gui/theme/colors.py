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

    def with_accent(self, accent: str, hover: str, pressed: str) -> "ThemeColors":
        return replace(self, accent=accent, accent_hover=hover, accent_pressed=pressed)


# ---------------------------------------------------------------------------
# Cobalt Flow palette (WorkSlop Desktop): deep cobalt gradient base, glass
# surfaces, electric-blue accent. Reflections are deliberately restrained —
# one thin glass border, no heavy top highlights.
# ---------------------------------------------------------------------------
DARK = ThemeColors(
    bg_primary="#0A1230",
    bg_secondary="#101B45",
    bg_tertiary="#16225A",
    bg_input="#0E1840",
    bg_elevated="#132052",

    text_primary="#FFFFFF",
    text_secondary="#9DB1DC",
    text_disabled="#5E6E99",
    text_inverse="#FFFFFF",

    accent="#3D7BFF",
    accent_hover="#5B93FF",
    accent_pressed="#2B5FD9",

    success="#30D158",
    error="#FF453A",
    error_hover="#FF5A50",
    error_pressed="#C2322A",
    warning="#FFD60A",

    border="#26346B",
    divider="#223063",

    scrollbar="#2A3A75",
    scrollbar_pressed="#3A4E96",
    selection="#3D7BFF",

    card_border="#2A3C7E",
    surface_hover="#1B2A66",
    danger_text="#FF453A",

    bg_gradient_start="#0C1C4E",
    bg_gradient_end="#050A20",
    glass_bg="rgba(35, 64, 150, 110)",
    glass_border="rgba(150, 180, 255, 40)",
    bubble="rgba(140, 175, 255, 26)",
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
