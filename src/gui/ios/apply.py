from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QProgressBar
)
import re

from src.gui.ios.components import (
    IOSSectionHeader, IOSCard, IOSPrimaryButton, IOSDangerButton,
    apply_full_nugget_chrome)
from src.gui.theme import ColorThemeManager, t
from src.gui.theme.colors import NUGGET_DARK
from src.gui.theme.styles import STYLES, FONT_FAMILY


def _qss(style_key: str, colors) -> str:
    """Render a global stylesheet template against an explicit palette."""
    payload = dict(colors.__dict__)
    payload["font_family"] = FONT_FAMILY
    return STYLES[style_key].format_map(payload)


def _nugget_primary_qss(c) -> str:
    """Primary-button recipe for the Full Nugget palette (the global
    template keys its background off text_primary, which is white in
    the Nugget palette — upstream Nugget primaries are accent blue)."""
    return (
        f"QPushButton {{ background-color: {c.accent}; border: none;"
        " border-radius: 14px; color: #FFFFFF; font-size: 15px;"
        " font-weight: 700; padding: 12px 20px; }"
        f"QPushButton:hover {{ background-color: {c.accent_hover}; color: #FFFFFF; }}"
        f"QPushButton:pressed {{ background-color: {c.accent_pressed}; color: #FFFFFF; }}"
        f"QPushButton:disabled {{ background-color: {c.bg_tertiary};"
        f" color: {c.text_disabled}; }}")


class IOSApplyPage(QWidget):
    """Apply / Remove tweaks — rebuilt from the classic Apply page using the
    iOS-style components."""
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")
        self._full_nugget = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        c = ColorThemeManager.instance().colors
        scroll.setStyleSheet(f"background-color: {c.bg_primary}; border: none;")
        self._scroll = scroll
        content = QWidget()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 32)
        content_layout.setSpacing(8)

        # --- Apply ---
        content_layout.addWidget(IOSSectionHeader(
            QCoreApplication.translate("Nugget", "Apply Tweaks")))

        apply_card = IOSCard()
        apply_layout = QVBoxLayout(apply_card)
        apply_layout.setContentsMargins(16, 12, 16, 12)
        apply_layout.setSpacing(8)

        apply_desc = QLabel(QCoreApplication.translate(
            "Nugget",
            "Applies every enabled tweak to your device. The device reboots "
            "when done — remember to turn Find My back on afterwards."))
        apply_desc.setWordWrap(True)
        apply_desc.setStyleSheet(f"color: {c.text_secondary}; font-size: 13px;")
        self.apply_desc = apply_desc
        apply_layout.addWidget(apply_desc)

        self.apply_btn = IOSPrimaryButton(QCoreApplication.translate(
            "Nugget", "Apply Tweaks"))
        self.apply_btn.clicked.connect(self.window.apply_tweaks_clicked)
        apply_layout.addWidget(self.apply_btn)
        content_layout.addWidget(apply_card)

        # --- Remove ---
        content_layout.addWidget(IOSSectionHeader(
            QCoreApplication.translate("Nugget", "Remove Tweaks")))

        remove_card = IOSCard()
        remove_layout = QVBoxLayout(remove_card)
        remove_layout.setContentsMargins(16, 12, 16, 12)
        remove_layout.setSpacing(8)

        remove_desc = QLabel(QCoreApplication.translate(
            "Nugget",
            "Restores the original values for the tweak pages you pick."))
        remove_desc.setWordWrap(True)
        remove_desc.setStyleSheet(f"color: {c.text_secondary}; font-size: 13px;")
        self.remove_desc = remove_desc
        remove_layout.addWidget(remove_desc)

        self.remove_btn = IOSDangerButton(QCoreApplication.translate(
            "Nugget", "Remove Tweaks"))
        self.remove_btn.clicked.connect(self.window.remove_tweaks_clicked)
        remove_layout.addWidget(self.remove_btn)
        content_layout.addWidget(remove_card)

        # --- Progress status ---
        content_layout.addWidget(IOSSectionHeader(
            QCoreApplication.translate("Nugget", "Progress")))

        status_card = IOSCard()
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(16, 12, 16, 12)
        status_layout.setSpacing(0)

        self.status_lbl = QLabel("")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setStyleSheet(f"color: {c.text_primary}; font-size: 14px;")
        status_layout.addWidget(self.status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet(t("dialog_progress_bar"))
        self.progress_bar.hide()
        status_layout.addWidget(self.progress_bar)
        content_layout.addWidget(status_card)

        content_layout.addStretch()

    def set_status(self, text: str):
        self.status_lbl.setText(text or "")
        match = re.search(r"(\d+(?:\.\d+)?)\s*%", text or "")
        if not text:
            self.progress_bar.hide()
        elif match:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(
                max(0, min(100, int(round(float(match.group(1)))))))
            self.progress_bar.show()
        else:
            # Phase-only line (no percent reported): the bar stays
            # visible and indeterminate, like the classic Apply page.
            self.progress_bar.setRange(0, 0)
            self.progress_bar.show()

    def set_busy(self, busy: bool):
        self.apply_btn.setEnabled(not busy)
        self.remove_btn.setEnabled(not busy)

    # ---------- Full Nugget palette (third interface) ----------

    def _palette(self):
        """Active colors: upstream Nugget dark in the Full Nugget
        interface, the themed WorkSlop palette everywhere else."""
        if getattr(self, "_full_nugget", False):
            return NUGGET_DARK
        return ColorThemeManager.instance().colors

    def set_full_nugget(self, enabled: bool):
        """Full Nugget (third interface) restyle: this page takes the
        Nugget-original dark palette like the other hosted pages
        (Daemons / Posterboard / Settings); the other interfaces keep
        the themed look untouched. Widgets, buttons and the apply flow
        are identical — colors only."""
        self._full_nugget = bool(enabled)
        self._retheme()

    def _retheme(self):
        c = self._palette()
        self._scroll.setStyleSheet(f"background-color: {c.bg_primary}; border: none;")
        self.apply_desc.setStyleSheet(f"color: {c.text_secondary}; font-size: 13px;")
        self.remove_desc.setStyleSheet(f"color: {c.text_secondary}; font-size: 13px;")
        self.status_lbl.setStyleSheet(f"color: {c.text_primary}; font-size: 14px;")
        self.progress_bar.setStyleSheet(_qss("dialog_progress_bar", c))
        self.apply_btn.setStyleSheet(
            _nugget_primary_qss(c) if self._full_nugget
            else _qss("primary_button", c))
        self.remove_btn.setStyleSheet(_qss("danger_button", c))
        apply_full_nugget_chrome(self, self._full_nugget)