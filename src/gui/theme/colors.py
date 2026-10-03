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
# Reference-blue palette (WorkSlop Desktop, Wave 10 layout rebuild): the
# bright-blue desktop-tool identity modeled on the user's reference —
# strong #0B65D8 header/footer bars (deepened in v5 so the blue/white
# identity never looks washed out), white content, light-grey device
# panel. The user-selected accent still drives primary actions through
# ACCENT_PRESETS.
# ---------------------------------------------------------------------------
WS_BLUE = ThemeColors(
    bg_primary="#FFFFFF",
    bg_secondary="#FFFFFF",
    bg_tertiary="#EAF1F8",
    bg_input="#F4F7FB",
    bg_elevated="#FFFFFF",

    text_primary="#1C2B3A",
    text_secondary="#5A6D80",
    text_disabled="#9DB0C1",
    text_inverse="#FFFFFF",

    accent="#0B65D8",
    accent_hover="#005CB8",
    accent_pressed="#004A94",

    success="#2FA84F",
    error="#E5484D",
    error_hover="#F0666A",
    error_pressed="#C03540",
    warning="#E8930C",

    border="#C4D6E8",
    divider="#D8E6F2",

    scrollbar="#9FBBD8",
    scrollbar_pressed="#7CA3CC",
    selection="#0B65D8",

    card_border="#C4D6E8",
    surface_hover="#DCEBF9",
    danger_text="#C03540",

    bg_gradient_start="#FFFFFF",
    bg_gradient_end="#E9F3FD",
    glass_bg="#FFFFFF",
    glass_border="#C4D6E8",
    bubble="rgba(11, 101, 216, 0.08)",

    menu_bg="#0B65D8",
    menu_text="#FFFFFF",
    menu_dim="#A8D4FF",
    menu_active_bg="#0053A8",
    menu_active_text="#FFFFFF",
    brand="#0B65D8",
    brand_dim="#2E7FC4",
)


# ---------------------------------------------------------------------------
# Workbench palette (Wave 10 first rebuild, rejected by the user as ugly;
# archived under riset/wave10/archive-old-ui/workbench-v1). Kept only so
# older constructions/imports keep working. Do not use for new UI.
# ---------------------------------------------------------------------------
WORKBENCH = ThemeColors(
    bg_primary="#E8EDF4",
    bg_secondary="#FFFFFF",
    bg_tertiary="#DCE5F0",
    bg_input="#F3F6FA",
    bg_elevated="#FFFFFF",

    text_primary="#101828",
    text_secondary="#526179",
    text_disabled="#93A1B5",
    text_inverse="#FFFFFF",

    accent="#0877FF",
    accent_hover="#2B8BFF",
    accent_pressed="#005BD1",

    success="#12B76A",
    error="#F04438",
    error_hover="#F97066",
    error_pressed="#D92D20",
    warning="#F79009",

    border="#C7D3E3",
    divider="#D9E2EE",

    scrollbar="#AFC0D6",
    scrollbar_pressed="#849DBB",
    selection="#0877FF",

    card_border="#D3DEEB",
    surface_hover="#EAF1FA",
    danger_text="#D92D20",

    bg_gradient_start="#E8EDF4",
    bg_gradient_end="#F7F9FC",
    glass_bg="#FFFFFF",
    glass_border="#D3DEEB",
    bubble="rgba(8, 119, 255, 0.05)",

    menu_bg="#0B1220",
    menu_text="#E6EDF7",
    menu_dim="#8FA1B9",
    menu_active_bg="#0877FF",
    menu_active_text="#FFFFFF",
    brand="#00BFA6",
    brand_dim="#63E6D2",
)


# ---------------------------------------------------------------------------
# Sky palette (retired in Wave 10): fresh light UI — comfortable white-blue
# tech theme. Kept only so older constructions/imports keep working; the app
# now ships WORKBENCH. Do not use for new UI.
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
# Nugget-original dark palette (Full Nugget interface, third UI): sampled
# from the vendored upstream form (src/qt/nugget741_ui.py) — window
# #1e1e1e, widgets #3b3b3b, borders #4B4B4B, text #FFFFFF, checked/accent
# #2860ca. Used ONLY by the pages the Full Nugget shell hosts (Daemons /
# Posterboard / Settings) while that interface is active; the other two
# interfaces keep the SKY palette untouched.
# ---------------------------------------------------------------------------
NUGGET_DARK = ThemeColors(
    bg_primary="#1e1e1e",
    bg_secondary="#3b3b3b",
    bg_tertiary="#2c2c2c",
    bg_input="#2c2c2c",
    bg_elevated="#262626",

    text_primary="#FFFFFF",
    text_secondary="#b8b8b8",
    text_disabled="#6e6e6e",
    text_inverse="#FFFFFF",

    accent="#2860ca",
    accent_hover="#3a74d6",
    accent_pressed="#1f4ea3",

    success="#34C759",
    error="#FF453A",
    error_hover="#FF6B62",
    error_pressed="#D93A30",
    warning="#FFD60A",

    border="#4B4B4B",
    divider="#3a3a3a",

    scrollbar="#3b3b3b",
    scrollbar_pressed="#4b4b4b",
    selection="#2860ca",

    card_border="#4B4B4B",
    surface_hover="#464646",
    danger_text="#FF6B62",

    bg_gradient_start="#1e1e1e",
    bg_gradient_end="#1e1e1e",
    glass_bg="#262626",
    glass_border="#4B4B4B",
    bubble="rgba(255, 255, 255, 0.06)",

    menu_bg="#1e1e1e",
    menu_text="#FFFFFF",
    menu_dim="#b8b8b8",
    menu_active_bg="#2860ca",
    menu_active_text="#FFFFFF",
    brand="#5B9BFF",
    brand_dim="#2860ca",
)


# ---------------------------------------------------------------------------
# Accent presets: (normal, hover, pressed)
# ---------------------------------------------------------------------------
ACCENT_PRESETS = {
    "blue":     ("#0B65D8", "#005CB8", "#004A94"),
    "purple":   ("#AF52DE", "#9B47C4", "#893DAB"),
    "pink":     ("#FF2D55", "#E6284D", "#CC2244"),
    "red":      ("#FF3B30", "#E6352B", "#CC2F26"),
    "orange":   ("#FF9500", "#E68600", "#CC7700"),
    "yellow":   ("#FFCC00", "#E6B800", "#CCA300"),
    "green":    ("#34C759", "#2EAF4E", "#289944"),
    "teal":     ("#5AC8FA", "#50B4E6", "#46A0D2"),
}
