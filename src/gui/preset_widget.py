"""Reusable preset banner widget.

Shows which preset is currently active (making presets explicit) and a
shortcut to open the preset manager. Used on both the classic and the
iOS-style home pages so the active state is always visible.
"""

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QToolButton,
)

from src.gui.theme import ColorThemeManager
from src.gui.brand_credits import beta_testers_html, make_beta_testers_label


class PresetBanner(QFrame):
    """A card that displays the active preset and a manage shortcut."""

    def __init__(self, ios_style: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("presetBanner")
        self.setFrameShape(QFrame.StyledPanel)
        self._ios_style = ios_style

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        self.caption_lbl = QLabel(QCoreApplication.translate(
            "Nugget", "Active preset"))
        text_col.addWidget(self.caption_lbl)

        self.active_lbl = QLabel(QCoreApplication.translate("Nugget", "AutoSave"))
        text_col.addWidget(self.active_lbl)

        layout.addLayout(text_col, 1)

        self.manage_btn = QPushButton(QCoreApplication.translate("Nugget", "Manage"), self)
        self.manage_btn.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.manage_btn)

        self._retheme()
        ColorThemeManager.instance().theme_changed.connect(self._retheme)

    def _retheme(self):
        c = ColorThemeManager.instance().colors
        if self._ios_style:
            self.setStyleSheet(f"""
                PresetBanner {{
                    background-color: {c.bg_secondary};
                    border-radius: 12px;
                    border: none;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                PresetBanner {{
                    background-color: {c.surface_hover};
                    border-radius: 10px;
                    border: none;
                }}
            """)
        self.caption_lbl.setStyleSheet(f"font-size: 12px; color: {c.text_secondary};")
        self.active_lbl.setStyleSheet(f"font-size: 17px; font-weight: 600; color: {c.text_primary};")
        self.manage_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {c.accent};
                font-size: 15px;
                font-weight: 600;
                border: none;
                padding: 8px 12px;
            }}
            QPushButton:hover {{ color: {c.accent_hover}; }}
        """)

    def set_active_preset(self, name: str, autosave: bool = True):
        """Show ``name``, or a placeholder when no preset is loaded.

        With autosave off there is nothing behind the banner, so claiming
        "AutoSave" would be a lie — the tweaks on screen belong to no preset.
        """
        if name:
            self.active_lbl.setText(name)
        elif autosave:
            self.active_lbl.setText(QCoreApplication.translate("Nugget", "AutoSave"))
        else:
            self.active_lbl.setText(QCoreApplication.translate("Nugget", "Not Saved"))


class PresetWidget(QWidget):
    """Home-screen container: header + active-preset banner + manage action.

    Tapping *Manage* opens an animated popup (``PresetPopup``) that lists every
    preset, lets the user pick one and exposes the full action set (save, load,
    delete, export, partial export, import, open in Settings). ``on_manage`` is
    only used as a fallback when no window is available to own the popup.
    """

    def __init__(self, window=None, on_manage=None, ios_style: bool = True,
                 parent=None):
        super().__init__(parent)
        self.window = window
        self._on_manage = on_manage
        self._ios_style = ios_style
        self._popup = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._header = QLabel()
        layout.addWidget(self._header)

        # Beta tester team block (user order 2026-10-03): rides with the
        # credit/attribution text above the preset banner on every Home
        # (in the Full Nugget interface it stacks directly under the
        # "UI reference" / "Based on" block). Plain names, no links.
        _c0 = ColorThemeManager.instance().colors
        self._beta_lbl = make_beta_testers_label(
            self, _c0.text_primary, _c0.accent)
        layout.addWidget(self._beta_lbl)

        # Third interface only: the Nugget UI credit (with the GitHub
        # button that the classic Nugget shell carries on its Home)
        # sits directly above the preset banner (user order
        # 2026-10-03), created lazily so the other interfaces never
        # see it.
        self._ref_lbl = None
        self._ref_row = None
        self._full_nugget = False

        self.banner = PresetBanner(ios_style=ios_style)
        self.banner.manage_btn.clicked.connect(self._on_manage_pressed)
        layout.addWidget(self.banner)

        self._retheme()
        ColorThemeManager.instance().theme_changed.connect(self._retheme)

    def _refresh_beta_label(self, text_color=None, link_color=None):
        """Recolor the beta tester block for the active palette (themed
        light, or the Full Nugget dark colors when overridden)."""
        if text_color is None:
            c = ColorThemeManager.instance().colors
            text_color, link_color = c.text_primary, c.accent
        self._beta_lbl.setText(beta_testers_html(text_color, link_color))

    def _retheme(self):
        if getattr(self, "_full_nugget", False):
            self.apply_full_nugget_style(True)
            return
        c = ColorThemeManager.instance().colors
        if self._ios_style:
            self._header.setText(QCoreApplication.translate("Nugget", "PRESETS"))
            self._header.setStyleSheet(
                f"font-size: 13px; font-weight: 600; color: {c.text_secondary};"
                "letter-spacing: 0.5px; padding-left: 4px;")
        else:
            self._header.setText(QCoreApplication.translate("Nugget", "Presets"))
            self._header.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {c.text_primary};")
        self._refresh_beta_label()
        self.banner._retheme()

    def apply_full_nugget_style(self, enabled: bool):
        """Dark upstream palette + the Nugget UI credit (UI-3 only).

        The classic Home sits on upstream's #1e1e1e backdrop there, so
        the WorkSlop palette's dark-on-light preset text was unreadable;
        on the original Nugget colors (#3b3b3b card, #e8e8e8/#FFFFFF
        text, #3b82f7 accent) the Presets block matches the page. Any
        other interface restores the normal themed look untouched.
        """
        self._full_nugget = bool(enabled)
        if not enabled:
            if self._ref_row is not None:
                self._ref_row.setVisible(False)
            if getattr(self, "_upstream_lbl", None) is not None:
                self._upstream_lbl.setVisible(False)
            c = ColorThemeManager.instance().colors
            self._header.setStyleSheet(
                f"font-size: 16px; font-weight: 600; color: {c.text_primary};")
            self._refresh_beta_label()
            self.banner._retheme()
            return
        if self._ref_row is None:
            from PySide6.QtCore import QSize
            from PySide6.QtGui import QIcon
            from webbrowser import open_new_tab
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(2, 0, 0, 0)
            row_layout.setSpacing(6)
            github_btn = QToolButton(row)
            github_btn.setObjectName("nuggetGithubBtn")
            github_btn.setIcon(QIcon(":/icon/github.svg"))
            github_btn.setIconSize(QSize(18, 18))
            github_btn.setCursor(Qt.PointingHandCursor)
            github_btn.setStyleSheet(
                "QToolButton { background: transparent; border: none; }"
                "QToolButton:hover { background-color: #3b3b3b;"
                " border-radius: 4px; }")
            github_btn.setToolTip(
                "github.com/adnan120hz/WorkSlop-Desktop-Version")
            github_btn.clicked.connect(lambda: open_new_tab(
                "https://github.com/adnan120hz/WorkSlop-Desktop-Version"))
            row_layout.addWidget(github_btn)
            self._ref_lbl = QLabel("UI reference: Nugget UI", row)
            self._ref_lbl.setStyleSheet("font-size: 12px; color: #cfcfcf;")
            row_layout.addWidget(self._ref_lbl)
            row_layout.addStretch(1)
            self.layout().insertWidget(1, row)
            self._ref_row = row
            # Upstream license attributions (user order 2026-10-03):
            # names + URLs are copied verbatim from the credits data
            # already recorded in the repo (Settings > About >
            # Credits, src/gui/dialogs/dialogs.py) — nothing invented.
            up_a = '<a style="text-decoration:none; color:#3b82f7" href='
            up_sep = '<span style="color:#cfcfcf"> · </span>'
            self._upstream_lbl = QLabel(self)
            self._upstream_lbl.setObjectName("upstreamCredits")
            self._upstream_lbl.setTextFormat(
                Qt.TextFormat.RichText)
            self._upstream_lbl.setOpenExternalLinks(True)
            self._upstream_lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextBrowserInteraction)
            self._upstream_lbl.setWordWrap(True)
            self._upstream_lbl.setText(
                '<span style="color:#cfcfcf">Based on: </span>'
                f'{up_a}"https://github.com/GoldenNugget-Team/GoldenNugget">'
                'GoldenNugget</a>'
                f'{up_sep}{up_a}"https://github.com/leminlimez/Nugget">'
                'Nugget by leminlimez</a><br/>'
                '<span style="color:#cfcfcf">Also credited: </span>'
                f'{up_a}"https://github.com/awesomenull-dev">awesomenull</a>'
                f'{up_sep}{up_a}"https://github.com/Wind0ws11Aero">'
                'Wind0ws11Aero</a>'
                f'{up_sep}{up_a}"https://discord.gg/gWtzTVhMvh">'
                'PosterRestore</a>'
                f'{up_sep}{up_a}"https://github.com/doronz88/pymobiledevice3">'
                'pymobiledevice3</a>'
                f'{up_sep}{up_a}"https://doc.qt.io/qtforpython-6/">PySide6</a>'
                f'{up_sep}{up_a}"https://github.com/Mikasa-san/QuietDaemon">'
                'Quiet Daemon (Mikasa-san)</a>'
                f'{up_sep}{up_a}"https://github.com/0xilis/python-aar-stuff">'
                'Snoolie</a>'
                f'{up_sep}{up_a}"https://github.com/f1shy-dev">f1shy-dev</a>'
                f'{up_sep}{up_a}"https://github.com/JJTech0130">JJTech0130</a>'
            )
            self._upstream_lbl.setStyleSheet(
                "font-size: 11px; padding: 0 2px;")
            self.layout().insertWidget(2, self._upstream_lbl)
        self._ref_row.setVisible(True)
        if getattr(self, "_upstream_lbl", None) is not None:
            self._upstream_lbl.setVisible(True)
        self._refresh_beta_label("#e8e8e8", "#3b82f7")
        self._header.setStyleSheet(
            "font-size: 16px; font-weight: 600; color: #e8e8e8;")
        b = self.banner
        b.setStyleSheet("""
            PresetBanner {
                background-color: #3b3b3b;
                border-radius: 10px;
                border: none;
            }
        """)
        b.caption_lbl.setStyleSheet("font-size: 12px; color: #bdbdbd;")
        b.active_lbl.setStyleSheet(
            "font-size: 17px; font-weight: 600; color: #FFFFFF;")
        b.manage_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #3b82f7;
                font-size: 15px;
                font-weight: 600;
                border: none;
                padding: 8px 12px;
            }
            QPushButton:hover { color: #5ea0ff; }
        """)

    def _on_manage_pressed(self):
        """Open the animated preset popup under the Manage button.

        Falls back to ``on_manage`` (navigate to the Settings page) when there
        is no window to own the popup, or when the popup cannot be created.
        """
        if self.window is not None and self._ios_style:
            try:
                from src.gui.ios.preset_menu import show_preset_popup
                if self._popup is not None:
                    try:
                        self._popup.close()
                    except RuntimeError:
                        # already destroyed by Qt when its parent went away
                        self._popup = None
                self._popup = show_preset_popup(
                    self.window, self.banner.manage_btn, parent=self.window)
                self._popup.closed.connect(self._forget_popup)
                return
            except Exception:
                # never let the banner break the home page: fall back
                self._popup = None
        if self._on_manage is not None:
            self._on_manage()

    def _forget_popup(self):
        popup, self._popup = self._popup, None
        if popup is not None:
            popup.deleteLater()

    def refresh(self):
        """Recompute and display the currently active preset."""
        name = self._current_preset_name()
        self.banner.set_active_preset(name, autosave=self._autosave_enabled())

    def _autosave_enabled(self) -> bool:
        if self.window is None:
            return True
        try:
            return bool(self.window.autosave_enabled())
        except Exception:
            return True

    def _current_preset_name(self) -> str:
        if self.window is None:
            return ""
        try:
            last = self.window.settings.value("last_loaded_preset", "", type=str)
        except Exception:
            last = ""
        if last:
            return last
        return ""
