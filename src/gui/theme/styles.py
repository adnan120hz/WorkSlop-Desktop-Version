"""Component stylesheet templates with ``{slot}`` placeholders.

Usage::

    from src.gui.theme.styles import STYLES
    widget.setStyleSheet(STYLES["card"].format_map(theme.colors.__dict__))
"""


# Single UI font used on every platform. The bundled Inter variable font is
# registered by main_app at startup as "Inter Variable", falling back to the
# OS default UI font if it is missing.
FONT_FAMILY = "Inter Variable"


_FONT_FAMILY_CACHE: str | None = None


def ui_font_family() -> str:
    """Return the UI font family, resolved once and cached."""
    global _FONT_FAMILY_CACHE
    if _FONT_FAMILY_CACHE is None:
        try:
            from PySide6.QtGui import QFontDatabase
            from PySide6.QtWidgets import QApplication
            if (QApplication.instance() is not None
                    and FONT_FAMILY in QFontDatabase.families()):
                _FONT_FAMILY_CACHE = FONT_FAMILY
            elif QApplication.instance() is not None:
                _FONT_FAMILY_CACHE = QFontDatabase.systemFont(
                    QFontDatabase.SystemFont.GeneralFont).family()
            else:
                _FONT_FAMILY_CACHE = FONT_FAMILY
        except Exception:
            _FONT_FAMILY_CACHE = FONT_FAMILY
    return _FONT_FAMILY_CACHE


# Backwards-compat alias (old name from the terminal theme era).
def mono_family() -> str:
    return ui_font_family()


STYLES = {
    # ---- Components ------------------------------------------------------
    "text_input_dialog": """
        QDialog {{ background-color: {bg_primary}; border: 1px solid {border}; }}
        QLabel {{ color: {text_primary}; font-size: 15px; }}
        QLineEdit {{
            background-color: {bg_input};
            border: 1px solid {border};
            border-radius: 10px;
            color: {text_primary};
            font-size: 15px;
            padding: 12px 16px;
            selection-background-color: {accent};
            selection-color: #FFFFFF;
        }}
        QPushButton {{
            background-color: {text_primary};
            border-radius: 10px;
            color: {text_inverse};
            font-size: 15px;
            font-weight: 700;
            padding: 12px 24px;
            border: none;
            min-width: 80px;
        }}
        QPushButton:hover {{ background-color: {accent}; color: #FFFFFF; }}
    """,

    "number_input_dialog": """
        QDialog {{ background-color: {bg_primary}; border: 1px solid {border}; }}
        QLabel {{ color: {text_primary}; font-size: 15px; }}
        QSpinBox {{
            background-color: {bg_input};
            border: 1px solid {border};
            border-radius: 10px;
            color: {text_primary};
            font-size: 15px;
            padding: 12px 16px;
            selection-background-color: {accent};
            selection-color: #FFFFFF;
        }}
        QSpinBox::up-button, QSpinBox::down-button {{ width: 0; }}
        QPushButton {{
            background-color: {text_primary};
            border-radius: 10px;
            color: {text_inverse};
            font-size: 15px;
            font-weight: 700;
            padding: 12px 24px;
            border: none;
            min-width: 80px;
        }}
        QPushButton:hover {{ background-color: {accent}; color: #FFFFFF; }}
    """,

    "section_header": (
        "font-size: 11px; font-weight: 800; color: {brand}; "
        "letter-spacing: 1.8px; padding-left: 2px; text-transform: uppercase;"
    ),

    # Header of an IOSCollapsibleSection: a compact workbench panel header,
    # distinct from the cards it controls.
    "collapsible_header": """
        QPushButton#iosCollapsibleHeader {{
            background-color: {bg_tertiary};
            border: 1px solid {card_border};
            border-radius: 10px;
            color: {text_primary};
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 1.2px;
            text-align: left;
            padding: 11px 14px;
        }}
        QPushButton#iosCollapsibleHeader:hover {{ background-color: {surface_hover}; color: {accent}; }}
        QPushButton#iosCollapsibleHeader:checked {{ color: {text_primary}; }}
    """,

    # Workbench card: dense white work surface with a fine steel border.
    "card": """
        IOSCard {{
            background-color: {bg_secondary};
            border-radius: 14px;
            border: 1px solid {card_border};
        }}
    """,

    "nav_bar": "background-color: {bg_secondary}; border-bottom: 1px solid {border};",

    "nav_back_btn": """
        QPushButton {{
            background: transparent;
            color: {accent};
            font-size: 14px;
            font-weight: 700;
            border: 1px solid transparent;
            padding: 7px 11px;
            border-radius: 8px;
        }}
        QPushButton:hover {{
            background-color: {surface_hover};
            border-color: {border};
            color: {accent_pressed};
        }}
        QPushButton:pressed {{
            background-color: {bg_tertiary};
            color: {accent_pressed};
        }}
    """,

    "nav_title": "font-size: 17px; font-weight: 800; color: {text_primary}; letter-spacing: 0.2px;",

    "nav_right_btn": """
        QPushButton {{
            background-color: {accent};
            color: #FFFFFF;
            font-size: 13px;
            font-weight: 800;
            border: none;
            padding: 8px 12px;
            border-radius: 8px;
        }}
        QPushButton:hover {{ background-color: {accent_hover}; }}
    """,

    "settings_row": """
        QPushButton {{
            background-color: transparent;
            border-radius: 8px;
            color: {text_primary};
            font-size: 14px;
            text-align: left;
            padding: 12px 14px;
            border: 1px solid transparent;
        }}
        QPushButton:hover {{ background-color: {surface_hover}; border-color: {card_border}; }}
    """,

    "primary_button": """
        QPushButton {{
            background-color: {accent};
            border-radius: 10px;
            color: #FFFFFF;
            font-size: 14px;
            font-weight: 800;
            border: 1px solid {accent_pressed};
            padding: 12px 20px;
        }}
        QPushButton:hover {{ background-color: {accent_hover}; color: #FFFFFF; }}
        QPushButton:pressed {{ background-color: {accent_pressed}; color: #FFFFFF; }}
        QPushButton:disabled {{ background-color: {bg_tertiary}; color: {text_disabled}; border-color: {border}; }}
    """,

    "danger_button": """
        QPushButton {{
            background-color: {error};
            border-radius: 14px;
            color: #ffffff;
            font-size: 15px;
            font-weight: 700;
            border: none;
            padding: 12px 20px;
        }}
        QPushButton:hover {{ background-color: {error_hover}; }}
        QPushButton:pressed {{ background-color: {error_pressed}; }}
        QPushButton:disabled {{ background-color: {bg_tertiary}; color: {text_disabled}; }}
    """,

    "confirm_dialog": """
        QDialog {{ background-color: {bg_primary}; border: 1px solid {border}; }}
        QLabel {{ color: {text_primary}; font-size: 15px; }}
        QLabel#confirmTitle {{ font-size: 17px; font-weight: 700; color: {text_primary}; }}
        QLabel#confirmMuted {{ color: {text_secondary}; font-size: 13px; }}
        QLabel#confirmRow {{ font-size: 14px; color: {text_primary}; }}
        QPushButton {{
            background-color: {text_primary};
            border-radius: 10px;
            color: {text_inverse};
            font-size: 15px;
            font-weight: 700;
            padding: 12px 24px;
            border: none;
            min-width: 110px;
        }}
        QPushButton:hover {{ background-color: {accent}; color: #FFFFFF; }}
        QPushButton#cancelBtn {{
            background-color: {bg_tertiary};
            color: {text_primary};
        }}
        QPushButton#cancelBtn:hover {{ background-color: {surface_hover}; color: {text_primary}; }}
    """,

    # IOSSwitch paints its own track/knob (it animates the knob position and
    # fades the track color), so there is no switch stylesheet here.

    "value_label": "color: {text_secondary}; font-size: 14px;",

    # ---- Preset popup (home screen, opened from the preset banner) ------
    "preset_popup": """
        QFrame#presetPopup {{
            background-color: {bg_elevated};
            border: 1px solid {card_border};
            border-radius: 14px;
        }}
    """,

    # A preset row is a QPushButton holding labels, so the row's own text is
    # empty; [checked="true"] is how the selection is shown.
    "preset_row": """
        QPushButton#presetRow {{
            background-color: transparent;
            border: none;
            border-radius: 10px;
            text-align: left;
            padding: 0px;
        }}
        QPushButton#presetRow:hover {{ background-color: {surface_hover}; }}
        QPushButton#presetRow:checked {{
            background-color: {surface_hover};
            border: 1px solid {accent};
        }}
    """,

    "preset_mini_button": """
        QPushButton#presetMiniButton {{
            background-color: {surface_hover};
            color: {text_primary};
            border: none;
            border-radius: 8px;
            font-size: 13px;
            padding: 0px 10px;
        }}
        QPushButton#presetMiniButton:hover {{ background-color: {divider}; }}
        QPushButton#presetMiniButton:disabled {{ color: {text_disabled}; }}
    """,

    "preset_mini_danger": """
        QPushButton#presetMiniButton {{
            background-color: {error_hover};
            color: {text_inverse};
            border: none;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            padding: 0px 14px;
        }}
        QPushButton#presetMiniButton:hover {{ background-color: {error}; }}
        QPushButton#presetMiniButton:disabled {{
            background-color: {surface_hover};
            color: {text_disabled};
        }}
    """,

    # ---- Pages -----------------------------------------------------------
    # Opaque workbench canvas. Every page owns its background now; there is
    # no animated sky layer behind text surfaces.
    "page_bg": "background-color: {bg_primary};",
    "scroll_area": "QScrollArea {{ background-color: {bg_primary}; border: none; }} QScrollArea > QWidget > QWidget {{ background-color: {bg_primary}; }}",

    # ---- Settings --------------------------------------------------------
    "settings_list": """
        QListWidget {{
            background-color: {bg_secondary};
            color: {text_primary};
            border: none;
            border-radius: 8px;
            padding: 4px;
        }}
        QListWidget::item:selected {{
            background-color: {scrollbar_pressed};
            color: {text_inverse};
            border-radius: 6px;
        }}
    """,

    "mini_button": """
        QPushButton {{
            background-color: {bg_tertiary};
            border-radius: 8px;
            color: {text_primary};
            border: none;
            padding: 6px 12px;
            font-size: 13px;
        }}
        QPushButton:hover {{ background-color: {surface_hover}; }}
    """,

    "combo_dropdown": """
        QComboBox {{
            background-color: {bg_secondary};
            border: none;
            border-radius: 8px;
            color: {text_primary};
            padding: 8px 12px;
            font-size: 10.5pt;
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {bg_secondary};
            border: 1px solid {divider};
            selection-background-color: {accent};
            selection-color: {text_inverse};
            border-radius: 8px;
            padding: 4px;
        }}
    """,

    # ---- PosterBoard -----------------------------------------------------
    "tab_bar": "background-color: {bg_primary}; border-top: 1px solid {border};",

    "tab_button_inactive": "color: {text_secondary}; background: transparent; border: none; font-weight: 600; font-size: 14px;",
    "tab_button_active": "color: {accent}; background: transparent; border: none; font-weight: 600; font-size: 14px;",

    "add_icon": "background-color: {bg_secondary}; border: 2px dashed {divider}; border-radius: 12px; color: {accent}; font-size: 28px; font-weight: 300;",

    "tendie_preview_btn": """
        QToolButton {{
            background-color: {bg_secondary};
            color: {accent};
            border: 1px solid {divider};
            border-radius: 8px;
            padding: 6px 12px;
            font-size: 13px;
        }}
        QToolButton:hover {{ background-color: {surface_hover}; }}
    """,

    "tendie_delete_btn": """
        QToolButton {{
            background-color: {bg_secondary};
            color: {error};
            border: 1px solid {divider};
            border-radius: 8px;
            padding: 6px 12px;
            font-size: 13px;
        }}
        QToolButton:hover {{ background-color: {error}; color: {text_inverse}; }}
    """,

    "template_preview": "background-color: {bg_secondary}; border: 1px solid {divider}; border-radius: 12px;",

    "reset_pb_button": """
        QPushButton {{
            background-color: {bg_tertiary};
            border-radius: 8px;
            color: {error};
            border: none;
            padding: 10px 16px;
            font-size: 14px;
        }}
        QPushButton:hover {{ background-color: {surface_hover}; }}
    """,

    "download_card_icon": "background-color: {accent}; border-radius: 10px; color: white; font-size: 20px;",

    "thumb_button": """
        QPushButton {{
            background-color: {bg_secondary};
            color: {accent};
            border-radius: 8px;
            border: none;
            padding: 8px 16px;
            font-size: 14px;
        }}
        QPushButton:hover {{ background-color: {surface_hover}; }}
    """,

    # ---- Home / device console ------------------------------------------
    "home_title": "font-size: 26px; font-weight: 800; color: {text_primary}; background-color: transparent;",
    "home_hero_title": (
        "font-size: 30px; font-weight: 850; color: {text_primary}; "
        "background-color: transparent;"
    ),
    "home_subtitle": "color: {text_secondary}; font-size: 13px; background-color: transparent;",

    # ---- Reference-blue shell (top header / device panel / footer) --------
    "device_side_panel": (
        "background-color: #FFFFFF; border-right: 1px solid {border};"
    ),
    "sidebar_device_header": (
        "font-size: 10px; font-weight: 800; color: {text_secondary}; "
        "letter-spacing: 1.5px; background-color: transparent;"
    ),
    "sidebar_device_combo": """
        QComboBox {{
            background-color: transparent;
            border: none;
            border-radius: 12px;
            color: {text_primary};
            padding: 4px 2px;
            font-size: 14px;
            font-weight: 800;
        }}
        QComboBox::drop-down {{ border: none; width: 20px; }}
        QComboBox::down-arrow {{
            image: url(:/icon/caret-down-fill.svg);
            width: 10px; height: 10px;
        }}
        QComboBox QAbstractItemView {{
            background-color: #FFFFFF;
            color: {text_primary};
            selection-background-color: {accent};
            selection-color: {text_inverse};
            border: 1px solid {border};
        }}
    """,
    "sidebar_nav_button": """
        QPushButton {{
            background-color: transparent;
            border: none;
            border-radius: 18px;
            color: {text_primary};
            font-size: 13px;
            font-weight: 600;
            text-align: left;
            padding-left: 11px;
        }}
        QPushButton:hover {{ background-color: #E2EFFC; }}
        QPushButton:checked {{
            background-color: #CDE6FB;
            color: {accent};
            font-weight: 800;
        }}
        QPushButton:disabled {{ color: {text_disabled}; }}
    """,
    "device_side_header": (
        "font-size: 11px; font-weight: 800; color: {text_secondary}; "
        "letter-spacing: 1.6px; background-color: transparent;"
    ),
    "device_row_name": (
        "font-size: 13px; font-weight: 700; color: {text_primary}; "
        "background-color: transparent;"
    ),
    "device_row_meta": (
        "font-size: 11px; color: {text_secondary}; background-color: transparent;"
    ),
    "info_label": (
        "color: {text_secondary}; font-size: 12px; background-color: transparent;"
    ),
    "info_value": (
        "color: {text_primary}; font-size: 12px; font-weight: 600; "
        "background-color: transparent;"
    ),
    "info_header": (
        "color: {text_primary}; font-size: 15px; font-weight: 800; "
        "background-color: transparent;"
    ),
    "storage_bar": """
        QProgressBar {{
            background-color: #E7EEF5;
            border: none;
            border-radius: 3px;
            height: 6px;
            text-align: center;
            font-size: 8px;
            color: transparent;
        }}
        QProgressBar::chunk {{ background-color: {accent}; border-radius: 3px; }}
    """,
    "action_tile_label": (
        "font-size: 11px; font-weight: 600; color: {text_primary}; "
        "background-color: transparent;"
    ),
    "phone_caption": (
        "font-size: 12px; font-weight: 700; color: {text_primary}; "
        "background-color: transparent;"
    ),
    "footer_text": (
        "font-size: 11px; font-weight: 600; color: #FFFFFF; "
        "background-color: transparent;"
    ),
    "footer_button": """
        QPushButton {{
            background-color: transparent;
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.65);
            border-radius: 12px;
            font-size: 11px;
            font-weight: 700;
            padding: 4px 14px;
        }}
        QPushButton:hover {{ background-color: rgba(255, 255, 255, 0.16); }}
        QPushButton:pressed {{ background-color: rgba(255, 255, 255, 0.26); }}
    """,
    "footer_light_text": (
        "font-size: 11px; font-weight: 600; color: {text_secondary}; "
        "background-color: transparent;"
    ),
    "footer_light_button": """
        QPushButton {{
            background-color: transparent;
            color: {accent};
            border: none;
            border-left: 1px solid {border};
            font-size: 11px;
            font-weight: 700;
            padding: 4px 12px;
        }}
        QPushButton:hover {{ background-color: #DCEBFA; }}
    """,
    "scroll_area_transparent": (
        "QScrollArea {{ background-color: transparent; border: none; }} "
        "QScrollArea > QWidget > QWidget {{ background-color: transparent; }}"
    ),
    "modern_card": """
        .QFrame {{
            background-color: #FFFFFF;
            border: 1px solid #C9DEF2;
            border-radius: 16px;
        }}
    """,
    "capacity_chip": (
        "background-color: #CFE7FD; color: {accent}; border: 1px solid #8FB9EA; "
        "border-radius: 10px; font-size: 11px; font-weight: 800; padding: 3px 10px;"
    ),
    "phone_link_button": """
        QPushButton {{
            background-color: transparent;
            border: none;
            color: {text_secondary};
            font-size: 12px;
            font-weight: 600;
            padding: 3px 8px;
        }}
        QPushButton:hover {{ color: {accent}; }}
        QPushButton:disabled {{ color: {text_disabled}; }}
    """,

    "dashboard_kicker": (
        "font-size: 10px; font-weight: 800; color: {brand}; "
        "letter-spacing: 2px; background-color: transparent;"
    ),
    "dashboard_heading": (
        "font-size: 26px; font-weight: 850; color: {text_primary}; "
        "background-color: transparent;"
    ),
    "dashboard_subheading": (
        "font-size: 13px; color: {text_secondary}; background-color: transparent;"
    ),
    "device_panel": """
        IOSCard {{
            background-color: {menu_bg};
            border-radius: 16px;
            border: 1px solid #1D2A3D;
            border-bottom: 4px solid {brand};
        }}
    """,
    "device_panel_kicker": (
        "font-size: 10px; font-weight: 800; color: {brand_dim}; "
        "letter-spacing: 2px; background-color: transparent;"
    ),
    "device_panel_title": (
        "font-size: 19px; font-weight: 800; color: #FFFFFF; "
        "background-color: transparent;"
    ),
    "device_panel_subtitle": (
        "font-size: 12px; color: {menu_dim}; background-color: transparent;"
    ),
    "device_meta_label": (
        "font-size: 9px; font-weight: 800; color: {menu_dim}; "
        "letter-spacing: 1.4px; background-color: transparent;"
    ),
    "device_meta_value": (
        "font-size: 13px; font-weight: 700; color: #FFFFFF; "
        "background-color: transparent;"
    ),
    "home_section_title": (
        "font-size: 12px; font-weight: 800; color: {text_primary}; "
        "letter-spacing: 1.4px; background-color: transparent;"
    ),
    "home_section_hint": (
        "font-size: 12px; color: {text_secondary}; background-color: transparent;"
    ),
    "catalogue_card": """
        IOSCard {{
            background-color: #FFFFFF;
            border-radius: 12px;
            border: 1px solid #E1ECF6;
        }}
    """,
    "catalogue_section": (
        "font-size: 12px; font-weight: 800; color: {text_primary}; "
        "background-color: transparent;"
    ),
    "catalogue_badge": (
        "font-size: 10px; font-weight: 700; color: #B3261E; "
        "background-color: #FDECEA; border: 1px solid #F3C2BF; "
        "border-radius: 8px; padding: 2px 8px;"
    ),
    "catalogue_chip": (
        "font-size: 11px; font-weight: 600; color: #0B4A8A; "
        "background-color: #EAF3FE; border: 1px solid #CFE3F8; "
        "border-radius: 9px; padding: 3px 9px;"
    ),

    "home_combo": """
        QComboBox {{
            background-color: {bg_secondary};
            border: 1px solid {border};
            border-radius: 10px;
            color: {text_primary};
            padding: 6px 10px;
            font-size: 10.5pt;
            font-weight: 600;
        }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox QAbstractItemView {{
            background-color: {bg_secondary};
            color: {text_primary};
            selection-background-color: {accent};
            selection-color: {text_inverse};
            border: 1px solid {border};
        }}
    """,

    "home_icon_button": """
        QPushButton {{
            background-color: {bg_secondary};
            color: {accent};
            border-radius: 12px;
            border: 1px solid {border};
            font-size: 16px;
            padding: 8px;
        }}
        QPushButton:hover {{ background-color: {surface_hover}; border-color: {accent}; }}
    """,

    # Home module tile: compact command card with a strong top rule, an icon
    # chip, and left-aligned operational copy. It is intentionally denser and
    # more tool-like than the retired centered Sky tiles.
    "home_tile": """
        IOSCard {{
            background-color: {bg_secondary};
            border-radius: 14px;
            border: 1px solid {card_border};
            border-top: 4px solid {brand};
        }}
        IOSCard:hover {{ border-color: {accent}; background-color: #F8FBFF; }}
    """,

    "home_tile_title": (
        "font-size: 15px; font-weight: 800; color: {text_primary}; "
        "background-color: transparent;"
    ),
    "home_tile_subtitle": (
        "color: {text_secondary}; font-size: 12px; "
        "background-color: transparent;"
    ),
    "home_tile_action": (
        "color: {accent}; font-size: 11px; font-weight: 800; "
        "letter-spacing: 1px; background-color: transparent;"
    ),
    "home_tile_icon": (
        "background-color: {bg_tertiary}; border: 1px solid {card_border}; "
        "border-radius: 12px;"
    ),

    "process_status_green": "color: {success}; font-size: 14px; font-weight: 500;",
    "process_status_red": "color: {error}; font-size: 14px; font-weight: 500;",
    "process_status_blue": "color: {accent}; font-size: 14px; font-weight: 500;",

    # ---- Daemons ---------------------------------------------------------
    "safety_note": "color: {danger_text}; font-size: 12px; font-style: italic;",

    # ---- Wallpaper downloader ---------------------------------------------
    "wp_card": """
        QFrame {{
            background-color: {bg_secondary};
            border-radius: 12px;
            border: none;
        }}
        QFrame:hover {{ background-color: {surface_hover}; }}
    """,

    "wp_name": "color: {text_primary}; font-size: 13px; font-weight: 600;",
    "wp_author": "color: {text_secondary}; font-size: 11px;",
    "wp_preview_bg": "background-color: {bg_tertiary};",
    "wp_loading_bg": "background-color: {bg_tertiary};",
    "wp_loading_text": "color: {text_disabled}; font-size: 12px;",

    "dialog_progress_bar": """
        QProgressBar {{
            background-color: {bg_tertiary};
            border: none;
            border-radius: 4px;
            height: 8px;
        }}
        QProgressBar::chunk {{
            background-color: {accent};
            border-radius: 4px;
        }}
    """,

    # ---- About dialog ----------------------------------------------------
    "about_separator": "background-color: {divider};",
    "about_desc": "color: {text_secondary}; font-size: 14px;",
    "about_credit_title": "color: {text_secondary}; font-size: 13px; font-weight: 600;",
    "about_link": "color: {accent}; font-size: 14px; border: none; background: transparent;",
    "about_link_hover": "color: {accent_hover}; font-size: 14px; border: none; background: transparent;",

    # ---- Interface picker ------------------------------------------------
    "picker_frame": """
        QFrame {{
            background-color: {bg_secondary};
            border-radius: 12px;
            border: 2px solid transparent;
        }}
        QFrame:hover {{ border-color: {accent}; }}
    """,

    # ---- Classic chrome (device bar) -------------------------------------

    "classic_bordered_btn": """
        QToolButton {{
            background: none;
            border: 1px solid {divider};
            color: {text_primary};
        }}
        QToolButton:hover {{
            background-color: {surface_hover};
        }}
        QToolButton:pressed {{
            background-color: {surface_hover};
            color: {text_primary};
        }}
    """,

    # ---- Global (main window stylesheet) ---------------------------------
    # Workbench: an opaque graphite workspace and white work surfaces keep
    # text crisp at any DPI. Inter remains the single UI font.
    "global": """
        QWidget {{ color: {text_primary}; background-color: {bg_primary}; spacing: 0px; font-family: '{font_family}'; }}
        QWidget:focus {{ outline: none; }}
        QWidget[cls=central] {{ background-color: {bg_primary}; border-radius: 0px; }}
        QLabel {{ font-size: 14px; }}
        QLabel[cls=dim] {{ color: {text_secondary}; }}
        QLabel[cls=term] {{ color: {brand}; }}
        QToolButton {{ background-color: {bg_tertiary}; border: 1px solid {card_border}; color: {text_primary}; font-size: 14px; min-height: 35px; icon-size: 16px; padding-left: 10px; padding-right: 10px; border-radius: 8px; }}
        QToolButton[cls=sidebarBtn] {{ background-color: transparent; icon-size: 24px; }}
        QToolButton:hover {{ background-color: {surface_hover}; }}
        QToolButton:pressed {{ background-color: {scrollbar_pressed}; color: {text_primary}; }}
        QToolButton:checked {{ background-color: {accent}; color: #FFFFFF; }}
        QCheckBox {{ spacing: 8px; font-size: 14px; }}
        QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {border}; background-color: {bg_tertiary}; }}
        QCheckBox::indicator:checked {{ background-color: {accent}; border: 1px solid {accent}; }}
        QRadioButton {{ spacing: 8px; font-size: 14px; }}
        QLineEdit {{ border: 1px solid {border}; border-radius: 8px; background-color: {bg_input}; color: {text_primary}; font-size: 14px; padding: 8px 10px; selection-background-color: {accent}; selection-color: #FFFFFF; }}
        QTextEdit {{ border: 1px solid {border}; border-radius: 8px; background-color: {bg_input}; color: {text_primary}; font-size: 14px; selection-background-color: {accent}; selection-color: #FFFFFF; }}
        QScrollBar:vertical {{ background: transparent; width: 9px; }}
        QScrollBar:horizontal {{ background: transparent; height: 9px; }}
        QScrollBar::handle {{ background: {scrollbar}; border-radius: 4px; }}
        QScrollBar::handle:hover {{ background: {scrollbar_pressed}; }}
        QScrollBar::handle:pressed {{ background: {scrollbar_pressed}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ background: none; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
        QSlider::groove:horizontal {{ background-color: {scrollbar}; height: 4px; border-radius: 2px; }}
        QSlider::handle:horizontal {{ background-color: {text_primary}; width: 10px; border-radius: 5px; }}
        QSlider::handle:horizontal:pressed {{ background-color: {accent}; }}
        QSlider::tick:horizontal {{ background-color: {scrollbar_pressed}; width: 1px; }}
        QProgressBar {{ background-color: {bg_tertiary}; border: 1px solid {card_border}; border-radius: 6px; text-align: center; color: {text_primary}; font-size: 12px; }}
        QProgressBar::chunk {{ background-color: {brand}; border-radius: 5px; }}
    """,
}
