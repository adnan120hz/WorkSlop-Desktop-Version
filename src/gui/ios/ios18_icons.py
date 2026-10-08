"""iOS 18 stock icon gallery (catwithabaloon pack), desktop table.

The same curated set the mobile app ships: 51 apps, Light artwork for
all of them, Dark artwork for 50 (the pack ships no Dark Shortcuts).
Picking a row's Light/Dark button adds that artwork to Icon Themes as
a normal IconTheme, so it rides the existing WebClip payload builder
(src/tweaks/icon_themes/icon_themes_tweak.py) unchanged: the target
column shows the exact HomeDomain restore path the builder writes,
``Library/WebClips/Cowabunga_<bundleID>,<displayName>.webclip/icon.png``.

Icon artwork: "iOS 18 App Icons by catwithabaloon"
(https://github.com/catwithabaloon/iOS-18-icon-pack) — see Credits.
PNGs live in files/ios18_icons/{Light,Dark}/ and ship with the app
via compile.py's ``--add-data=files/:files``. The pack's Tinted
variant and artwork that could not be identified with certainty are
not shipped, exactly as on mobile.
"""
import os

from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
)

from src.controllers.files_handler import get_bundle_files
from src.gui.theme import ColorThemeManager
from src.tweaks.tweaks import tweaks, TweakID
from src.tweaks.icon_themes.icon_theme import IconTheme


def tr(text: str) -> str:
    return QCoreApplication.translate("Nugget", text)


# (display name, bundle id, asset slug) — identical to IOS18IconCatalog
# in the mobile app (WorkSlop/IOS18Icons.swift), bundle IDs verified
# against the iTunes lookup / system constants there.
IOS18_ICONS = [
    ("Shortcuts", "com.apple.shortcuts", "shortcuts"),
    ("App Store", "com.apple.AppStore", "app-store"),
    ("Settings", "com.apple.Preferences", "settings"),
    ("Numbers", "com.apple.Numbers", "numbers"),
    ("Pages", "com.apple.Pages", "pages"),
    ("Keynote", "com.apple.Keynote", "keynote"),
    ("Books", "com.apple.iBooks", "books"),
    ("Calculator", "com.apple.calculator", "calculator"),
    ("Calendar", "com.apple.mobilecal", "calendar"),
    ("Camera", "com.apple.camera", "camera"),
    ("Music Classical", "com.apple.music.classical", "music-classical"),
    ("Clock", "com.apple.mobiletimer", "clock"),
    ("Compass", "com.apple.compass", "compass"),
    ("Contacts", "com.apple.AddressBook", "contacts"),
    ("FaceTime", "com.apple.facetime", "facetime"),
    ("Files", "com.apple.DocumentsApp", "files"),
    ("Clips", "com.apple.clips", "clips"),
    ("Find My", "com.apple.findmy", "find-my"),
    ("Fitness", "com.apple.Fitness", "fitness"),
    ("GarageBand", "com.apple.mobilegarageband", "garageband"),
    ("Health", "com.apple.Health", "health"),
    ("Home", "com.apple.Home", "home"),
    ("Magnifier", "com.apple.Magnifier", "magnifier"),
    ("Mail", "com.apple.mobilemail", "mail"),
    ("Maps", "com.apple.Maps", "maps"),
    ("Measure", "com.apple.measure", "measure"),
    ("Music", "com.apple.Music", "music"),
    ("News", "com.apple.news", "news"),
    ("Notes", "com.apple.mobilenotes", "notes"),
    ("Passwords", "com.apple.Passwords", "passwords"),
    ("Phone", "com.apple.mobilephone", "phone"),
    ("Photos", "com.apple.mobileslideshow", "photos"),
    ("Podcasts", "com.apple.podcasts", "podcasts"),
    ("Reminders", "com.apple.reminders", "reminders"),
    ("Apple TV Remote", "com.apple.TVRemote", "apple-tv-remote"),
    ("Safari", "com.apple.mobilesafari", "safari"),
    ("Stocks", "com.apple.stocks", "stocks"),
    ("Apple Store", "com.apple.store.Jolly", "apple-store"),
    ("Swift Playgrounds", "com.apple.Playgrounds", "swift-playgrounds"),
    ("TestFlight", "com.apple.TestFlight", "testflight"),
    ("Tips", "com.apple.tips", "tips"),
    ("Translate", "com.apple.Translate", "translate"),
    ("Voice Memos", "com.apple.VoiceMemos", "voice-memos"),
    ("Wallet", "com.apple.Passbook", "wallet"),
    ("Watch", "com.apple.Bridge", "watch"),
    ("Weather", "com.apple.weather", "weather"),
    ("Messages", "com.apple.MobileSMS", "messages"),
    ("iMovie", "com.apple.iMovie", "imovie"),
    ("Apple Sports", "com.apple.sports", "apple-sports"),
    ("TV", "com.apple.tv", "tv"),
    ("Shazam", "com.shazam.Shazam", "shazam"),
]


def icon_asset_path(slug: str, dark: bool) -> str:
    variant = "Dark" if dark else "Light"
    return get_bundle_files(f"files/ios18_icons/{variant}/{slug}.png")


def webclip_target(bundle_id: str, display_name: str, tweak) -> str:
    """The exact on-device spot the icon lands in, as written by
    IconThemesTweak.apply_tweak (HomeDomain restore path)."""
    safe_name = tweak.sanitize_display_name(display_name)
    return (f"Library/WebClips/Cowabunga_{bundle_id},{safe_name}"
            f".webclip/icon.png (HomeDomain)")


class IOS18IconsPage(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")

        self._c = ColorThemeManager.instance().colors
        self._pixmaps: dict[str, QPixmap] = {}
        self._add_buttons: list[QPushButton] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 24)
        layout.setSpacing(10)

        hint = QLabel(tr(
            "Stock iOS 18 app icons from the catwithabaloon icon pack. "
            "Use Light or Dark on a row to add that artwork to Icon "
            "Themes; it is delivered as a WebClip to the target shown, "
            "exactly like any other icon theme."))
        hint.setWordWrap(True)
        self._hint = hint
        layout.addWidget(hint)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        tweak = tweaks[TweakID.IconThemes]
        self._table = QTableWidget(len(IOS18_ICONS), 6)
        self._table.setObjectName("ios18IconTable")
        self._table.setHorizontalHeaderLabels([
            tr("Light"), tr("Dark"), tr("App"), tr("Bundle ID"),
            tr("Target on device"), tr("Add"),
        ])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 64)
        self._table.setColumnWidth(1, 64)
        self._table.setColumnWidth(5, 132)

        for row, (name, bundle_id, slug) in enumerate(IOS18_ICONS):
            self._table.setRowHeight(row, 56)
            self._table.setCellWidget(
                row, 0, self._icon_cell(slug, dark=False))
            self._table.setCellWidget(
                row, 1, self._icon_cell(slug, dark=True))
            self._table.setItem(row, 2, QTableWidgetItem(name))
            self._table.setItem(row, 3, QTableWidgetItem(bundle_id))
            self._table.setItem(
                row, 4, QTableWidgetItem(
                    webclip_target(bundle_id, name, tweak)))
            self._table.setCellWidget(
                row, 5, self._add_cell(name, bundle_id, slug))

        layout.addWidget(self._table, 1)

        credit = QLabel(tr(
            "Icon artwork: iOS 18 App Icons by catwithabaloon "
            "(github.com/catwithabaloon/iOS-18-icon-pack)."))
        credit.setWordWrap(True)
        self._credit = credit
        layout.addWidget(credit)

        self._retheme()

    # -- cells ---------------------------------------------------------
    def _pixmap(self, slug: str, dark: bool) -> QPixmap:
        path = icon_asset_path(slug, dark)
        pix = self._pixmaps.get(path)
        if pix is None:
            pix = QPixmap(path)
            self._pixmaps[path] = pix
        return pix

    def _icon_cell(self, slug: str, dark: bool) -> QWidget:
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        pix = self._pixmap(slug, dark)
        if pix.isNull():
            lbl.setText("—")
        else:
            lbl.setPixmap(pix.scaled(
                44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        return lbl

    def _add_cell(self, name: str, bundle_id: str, slug: str) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(4, 4, 4, 4)
        row.setSpacing(6)
        for label, dark in ((tr("Light"), False), (tr("Dark"), True)):
            btn = QPushButton(label)
            btn.setObjectName("ios18AddBtn")
            btn.setCursor(Qt.PointingHandCursor)
            available = os.path.isfile(icon_asset_path(slug, dark))
            btn.setEnabled(available)
            if available:
                btn.clicked.connect(
                    lambda _=False, n=name, b=bundle_id, s=slug, d=dark:
                    self._use_icon(n, b, s, d))
            row.addWidget(btn)
            self._add_buttons.append(btn)
        return box

    # -- actions -------------------------------------------------------
    def _use_icon(self, name: str, bundle_id: str, slug: str, dark: bool):
        path = icon_asset_path(slug, dark)
        if not os.path.isfile(path):
            return
        tweak = tweaks[TweakID.IconThemes]
        theme = IconTheme(bundle_id=bundle_id, display_name=name,
                          icon_path=path)
        if not tweak.store_icon(theme):
            QMessageBox.warning(
                self.window,
                tr("Warning"),
                tr("Could not store the icon file in the persistent "
                   "folder. The theme may not apply reliably."))
        tweak.add_theme(theme)
        tweak.set_enabled(True)
        page = getattr(self.window, "ios_iconthemes", None)
        if page is not None:
            page.refresh_themes()
        self._status.setText(tr("Added {0} ({1}) to Icon Themes.").format(
            name, tr("Dark") if dark else tr("Light")))

    # -- theming -------------------------------------------------------
    def _retheme(self):
        c = ColorThemeManager.instance().colors
        self._c = c
        self.setStyleSheet(f"background-color: {c.bg_primary};")
        self._hint.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 13px;"
            " background-color: transparent;")
        self._status.setStyleSheet(
            f"color: {c.accent}; font-size: 13px;"
            " background-color: transparent;")
        self._credit.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 12px;"
            " background-color: transparent;")
        self._table.setStyleSheet(f"""
            QTableWidget#ios18IconTable {{
                background-color: {c.bg_secondary};
                border: 1px solid {c.border};
                border-radius: 12px;
                gridline-color: {c.divider};
                color: {c.text_primary};
                font-size: 13px;
            }}
            QTableWidget#ios18IconTable::item {{
                padding: 4px 8px;
                border: none;
            }}
            QTableWidget#ios18IconTable::item:selected {{
                background-color: {c.surface_hover};
                color: {c.text_primary};
            }}
            QHeaderView::section {{
                background-color: {c.bg_tertiary};
                color: {c.text_secondary};
                border: none;
                padding: 8px;
                font-size: 13px;
                font-weight: 600;
            }}
        """)
        for btn in self._add_buttons:
            btn.setStyleSheet(f"""
                QPushButton#ios18AddBtn {{
                    background-color: {c.bg_input};
                    border: 1px solid {c.border};
                    border-radius: 8px;
                    color: {c.accent};
                    font-size: 12px;
                    font-weight: 600;
                    padding: 6px 8px;
                }}
                QPushButton#ios18AddBtn:hover {{ background-color: {c.surface_hover}; }}
                QPushButton#ios18AddBtn:disabled {{ color: {c.text_disabled}; }}
            """)
