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

    # Sky theme (WorkSlop Desktop): white navigation rail on a light-blue
    # body. Defaults keep older constructions working.
    menu_bg: str = "#FFFFFF"
    menu_text: str = "#0A0A0A"
    menu_dim: str = "#6B6B6B"
    menu_active_bg: str = "#0A0A0A"
    menu_active_text: str = "#FFFFFF"
    brand: str = "#00E676"
    brand_dim: str = "#00884a"

    def with_accent(self, accent: str, hover: str, pressed: str) -> "ThemeColors":
        return replace(self, accent=accent, accent_hover=hover, accent_pressed=pressed)


# ---------------------------------------------------------------------------
# Sky palette (WorkSlop Desktop): fresh light UI — comfortable white-blue
# tech theme. Soft blue-white body, deep navy text, Apple-blue accents.
# Flat and solid — no gradients, no blur, no translucency on text surfaces.
# ---------------------------------------------------------------------------
SKY = ThemeColors(
    bg_primary="#F2F7FF",
    bg_secondary="#FFFFFF",
    bg_tertiary="#E7F0FE",
    bg_input="#FFFFFF",
    bg_elevated="#FFFFFF",

    text_primary="#0B1E3A",
    text_secondary="#4A5F7F",
    text_disabled="#9AA9C0",
    text_inverse="#FFFFFF",

    accent="#007AFF",
    accent_hover="#3395FF",
    accent_pressed="#005FCC",

    success="#16A34A",
    error="#E5484D",
    error_hover="#F0666A",
    error_pressed="#C03540",
    warning="#D99400",

    border="#D7E3F5",
    divider="#E3ECFA",

    scrollbar="#C3D6EE",
    scrollbar_pressed="#A9C4E8",
    selection="#007AFF",

    card_border="#DCE7F8",
    surface_hover="#EAF2FE",
    danger_text="#E5484D",

    bg_gradient_start="#F2F7FF",
    bg_gradient_end="#E4EEFD",
    glass_bg="#FFFFFF",
    glass_border="#DCE7F8",
    bubble="rgba(0, 122, 255, 0.05)",

    menu_bg="#FFFFFF",
    menu_text="#0B1E3A",
    menu_dim="#7A8CA8",
    menu_active_bg="#007AFF",
    menu_active_text="#FFFFFF",
    brand="#007AFF",
    brand_dim="#5AA9FF",
)


# ---------------------------------------------------------------------------
# Terminal palette (retired): soft-black body. Kept for reference; the app
# now ships the SKY light theme. Do not use for new UI.
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
    brand="#00C853",
    brand_dim="#007A43",
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
