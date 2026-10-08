import os

from PySide6.QtCore import Qt, QCoreApplication, QSize
from PySide6.QtGui import QPixmap, QPixmapCache
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QPushButton, QToolButton, QFileDialog, QDialog, QDialogButtonBox,
    QLineEdit, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
)

from src.controllers.files_handler import get_bundle_files
from src.gui.ios.components import IOSCard
from src.gui.theme import ColorThemeManager, theme_icon
from src.gui.dialogs.icon_pack_downloader import IconPackDownloaderDialog
from src.gui.dialogs.app_list_dialog import AppListExportDialog
from src.tweaks.tweaks import tweaks, TweakID
from src.tweaks.icon_themes.icon_theme import IconTheme
from src.tweaks.icon_themes.icon_themes_tweak import build_pack_hash_index


def _tr(text: str) -> str:
    return QCoreApplication.translate("Nugget", text)


# iOS 18 stock icon gallery (catwithabaloon pack), shown as a table
# inside this page. The same curated set the mobile app ships: 51
# apps, Light artwork for all of them, Dark artwork for 50 (the pack
# ships no Dark Shortcuts). Picking a row's Light/Dark button — or
# Add All — adds that artwork to Icon Themes as a normal IconTheme,
# so it rides the existing WebClip payload builder
# (src/tweaks/icon_themes/icon_themes_tweak.py) unchanged: the target
# column shows the exact HomeDomain restore path the builder writes,
# ``Library/WebClips/WorkSlop_<bundleID>,<displayName>.webclip/icon.png``.
#
# Icon artwork: "iOS 18 App Icons by catwithabaloon"
# (https://github.com/catwithabaloon/iOS-18-icon-pack) — see Credits.
# PNGs live in files/ios18_icons/{Light,Dark}/ and ship with the app
# via compile.py's ``--add-data=files/:files``. The pack's Tinted
# variant and artwork that could not be identified with certainty are
# not shipped, exactly as on mobile.

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


def ios18_pack_hash_index() -> dict:
    """sha256 -> catalog entry for every bundled iOS 18 icon file.

    Lets a user-supplied pack zip (whose files have generic names like
    ``App Icon-37.png``) be matched to the catalog by content instead
    of by name — see IconThemesTweak.import_pack_zip_matched.
    """
    catalog = [
        (bundle_id, name, icon_asset_path(slug, False),
         icon_asset_path(slug, True))
        for name, bundle_id, slug in IOS18_ICONS
    ]
    return build_pack_hash_index(catalog)


def webclip_target(bundle_id: str, display_name: str, tweak) -> str:
    """The exact on-device spot the icon lands in, as written by
    IconThemesTweak.apply_tweak (HomeDomain restore path)."""
    safe_name = tweak.sanitize_display_name(display_name)
    return (f"Library/WebClips/WorkSlop_{bundle_id},{safe_name}"
            f".webclip/icon.png (HomeDomain)")


class IOSIconThemesPage(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")

        self._c = ColorThemeManager.instance().colors

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._scroll = scroll
        content = QWidget()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(16, 16, 16, 32)
        self.content_layout.setSpacing(8)

        hint = QLabel(QCoreApplication.translate(
            "Nugget",
            "Theme a home screen icon with a custom image and label without "
            "jailbreaking. Tapping the icon still opens the real app. "
            "WebClips launch \"Add to Home Screen\" shortcuts, so existing "
            "icon shortcuts stay untouched — remove disabled apps before "
            "themes to avoid collisions. Applying icon themes restarts the "
            "iPhone so the new icons appear."))
        hint.setWordWrap(True)
        self._hint = hint
        self.content_layout.addWidget(hint)

        reset_btn = QPushButton(QCoreApplication.translate(
            "Nugget", "Reset Icon Themes"))
        reset_btn.setObjectName("resetIconThemes")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.clicked.connect(self._reset_themes)
        self._reset_btn = reset_btn
        self.content_layout.addWidget(reset_btn)

        download_btn = QPushButton(QCoreApplication.translate(
            "Nugget", "Download Icon Packs"))
        download_btn.setObjectName("downloadIconPacks")
        download_btn.setCursor(Qt.PointingHandCursor)
        download_btn.clicked.connect(self.show_download_packs)
        self._download_btn = download_btn
        self.content_layout.addWidget(download_btn)

        import_zip_btn = QPushButton(QCoreApplication.translate(
            "Nugget", "Import Icon Pack (.zip)…"))
        import_zip_btn.setObjectName("importIconPackZip")
        import_zip_btn.setCursor(Qt.PointingHandCursor)
        import_zip_btn.clicked.connect(self.show_import_pack_zip)
        self._import_zip_btn = import_zip_btn
        self.content_layout.addWidget(import_zip_btn)

        apps_btn = QPushButton(QCoreApplication.translate(
            "Nugget", "Apps on iPhone"))
        apps_btn.setObjectName("appsOnIphone")
        apps_btn.setCursor(Qt.PointingHandCursor)
        apps_btn.clicked.connect(self.show_app_list_export)
        self._apps_btn = apps_btn
        self.content_layout.addWidget(apps_btn)

        self.themes_placeholder = QLabel(QCoreApplication.translate(
            "Nugget", "No icon themes yet. Tap + Add Icon or download a pack."))
        self.themes_placeholder.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(self.themes_placeholder)

        self._themes_box = QVBoxLayout()
        self._themes_box.setSpacing(8)
        self.content_layout.addLayout(self._themes_box)

        # --- iOS 18 stock icons (catwithabaloon pack) ---
        self._ios18_add_buttons: list[QPushButton] = []

        self.content_layout.addSpacing(16)
        ios18_header = QLabel(_tr("iOS 18 Icons"))
        ios18_header.setObjectName("ios18Header")
        self._ios18_header = ios18_header
        self.content_layout.addWidget(ios18_header)

        ios18_hint = QLabel(_tr(
            "Stock iOS 18 app icons from the catwithabaloon icon pack. "
            "Use Light or Dark on a row to add that artwork to Icon "
            "Themes, or Add All to add every app that is not in Icon "
            "Themes yet (Light artwork); it is delivered as a WebClip "
            "to the target shown, exactly like any other icon theme."))
        ios18_hint.setWordWrap(True)
        self._ios18_hint = ios18_hint
        self.content_layout.addWidget(ios18_hint)

        add_all_btn = QPushButton(_tr("Add All"))
        add_all_btn.setObjectName("ios18AddAll")
        add_all_btn.setCursor(Qt.PointingHandCursor)
        add_all_btn.clicked.connect(self._use_all_icons)
        self._ios18_add_all_btn = add_all_btn
        self.content_layout.addWidget(add_all_btn)

        self._ios18_status = QLabel("")
        self._ios18_status.setWordWrap(True)
        self.content_layout.addWidget(self._ios18_status)

        self._ios18_table = self._build_ios18_table()
        self.content_layout.addWidget(self._ios18_table)

        ios18_credit = QLabel(_tr(
            "Icon artwork: iOS 18 App Icons by catwithabaloon "
            "(github.com/catwithabaloon/iOS-18-icon-pack)."))
        ios18_credit.setWordWrap(True)
        self._ios18_credit = ios18_credit
        self.content_layout.addWidget(ios18_credit)

        self.content_layout.addStretch()

        self._retheme()
        self.refresh_themes()

    # -- iOS 18 stock icon table ----------------------------------------
    def _build_ios18_table(self) -> QTableWidget:
        tweak = tweaks[TweakID.IconThemes]
        table = QTableWidget(len(IOS18_ICONS), 6)
        table.setObjectName("ios18IconTable")
        table.setHorizontalHeaderLabels([
            _tr("Light"), _tr("Dark"), _tr("App"), _tr("Bundle ID"),
            _tr("Target on device"), _tr("Add"),
        ])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(0, 64)
        table.setColumnWidth(1, 64)
        table.setColumnWidth(5, 132)

        for row, (name, bundle_id, slug) in enumerate(IOS18_ICONS):
            table.setRowHeight(row, 56)
            table.setCellWidget(row, 0, self._icon_cell(slug, dark=False))
            table.setCellWidget(row, 1, self._icon_cell(slug, dark=True))
            table.setItem(row, 2, QTableWidgetItem(name))
            table.setItem(row, 3, QTableWidgetItem(bundle_id))
            table.setItem(row, 4, QTableWidgetItem(
                webclip_target(bundle_id, name, tweak)))
            table.setCellWidget(
                row, 5, self._add_cell(name, bundle_id, slug))

        # The page itself scrolls, so the table shows every row and
        # never grows its own vertical scrollbar.
        rows_h = sum(table.rowHeight(r) for r in range(table.rowCount()))
        table.setFixedHeight(max(header.height(), 30) + rows_h + 2)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        return table

    def _pixmap(self, slug: str, dark: bool) -> QPixmap:
        """44px thumbnail for the iOS 18 icons table, via QPixmapCache.

        The page is built lazily on first navigation, so decoding happens
        on first open — and only the display-size thumbnail is cached,
        never the full-res pixmap (the old dict pinned all 102 of them).
        """
        path = icon_asset_path(slug, dark)
        key = f"ios18icon:{path}"
        pix = QPixmapCache.find(key)
        if pix is None:
            full = QPixmap(path)
            if full.isNull():
                return full
            pix = full.scaled(
                44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            QPixmapCache.insert(key, pix)
        return pix

    def _icon_cell(self, slug: str, dark: bool) -> QWidget:
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        pix = self._pixmap(slug, dark)
        if pix.isNull():
            lbl.setText("—")
        else:
            lbl.setPixmap(pix)
        return lbl

    def _add_cell(self, name: str, bundle_id: str, slug: str) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(4, 4, 4, 4)
        row.setSpacing(6)
        for label, dark in ((_tr("Light"), False), (_tr("Dark"), True)):
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
            self._ios18_add_buttons.append(btn)
        return box

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
                _tr("Warning"),
                _tr("Could not store the icon file in the persistent "
                    "folder. The theme may not apply reliably."))
        tweak.add_theme(theme)
        tweak.set_enabled(True)
        self.refresh_themes()
        self._ios18_status.setText(_tr(
            "Added {0} ({1}) to Icon Themes.").format(
                name, _tr("Dark") if dark else _tr("Light")))

    def _use_all_icons(self):
        tweak = tweaks[TweakID.IconThemes]
        existing = {t.bundle_id for t in tweak.themes}
        added = 0
        store_failed = 0
        for name, bundle_id, slug in IOS18_ICONS:
            if bundle_id in existing:
                continue
            path = icon_asset_path(slug, dark=False)
            if not os.path.isfile(path):
                continue
            theme = IconTheme(bundle_id=bundle_id, display_name=name,
                              icon_path=path)
            if not tweak.store_icon(theme):
                store_failed += 1
            tweak.add_theme(theme)
            added += 1
        if added:
            tweak.set_enabled(not tweak.is_empty())
            self.refresh_themes()
        if added and store_failed:
            self._ios18_status.setText(_tr(
                "Added {0} iOS 18 icons (Light) to Icon Themes; {1} "
                "could not be stored (those themes may not apply "
                "reliably).").format(added, store_failed))
        elif added:
            self._ios18_status.setText(_tr(
                "Added {0} iOS 18 icons (Light) to Icon Themes.").format(
                    added))
        elif store_failed:
            self._ios18_status.setText(_tr(
                "Nothing new was added, and {0} icons could not be "
                "stored (those themes may not apply reliably).").format(
                    store_failed))
        else:
            self._ios18_status.setText(_tr(
                "Every iOS 18 icon is already in Icon Themes."))

    def _reset_themes(self):
        reply = QMessageBox.question(
            self.window,
            QCoreApplication.translate("Nugget", "Reset Icon Themes"),
            QCoreApplication.translate(
                "Nugget",
                "Remove all icon themes from WorkSlop Desktop? The themed "
                "home-screen icons already on the device are not touched."),
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.StandardButton.Cancel)
        if reply != QMessageBox.StandardButton.Yes:
            return
        tweak = tweaks[TweakID.IconThemes]
        tweak.themes = []
        tweak.set_enabled(False)
        self.refresh_themes()

    def _retheme(self):
        c = ColorThemeManager.instance().colors
        self._c = c
        self._scroll.setStyleSheet(
            f"background-color: {c.bg_primary}; border: none;")
        self._hint.setStyleSheet(f"color: {c.text_secondary}; font-size: 13px;")
        self._download_btn.setStyleSheet(f"""
            QPushButton#downloadIconPacks {{
                background-color: {c.bg_secondary};
                border: 1px solid {c.border};
                border-radius: 12px;
                color: {c.accent};
                font-size: 14px;
                font-weight: 600;
                padding: 12px;
            }}
            QPushButton#downloadIconPacks:hover {{ background-color: {c.surface_hover}; }}
        """)
        self._import_zip_btn.setStyleSheet(f"""
            QPushButton#importIconPackZip {{
                background-color: {c.bg_secondary};
                border: 1px solid {c.border};
                border-radius: 12px;
                color: {c.accent};
                font-size: 14px;
                font-weight: 600;
                padding: 12px;
            }}
            QPushButton#importIconPackZip:hover {{ background-color: {c.surface_hover}; }}
        """)
        self._apps_btn.setStyleSheet(f"""
            QPushButton#appsOnIphone {{
                background-color: {c.bg_secondary};
                border: 1px solid {c.border};
                border-radius: 12px;
                color: {c.accent};
                font-size: 14px;
                font-weight: 600;
                padding: 12px;
            }}
            QPushButton#appsOnIphone:hover {{ background-color: {c.surface_hover}; }}
        """)
        self.themes_placeholder.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 15px; padding: 24px 0;")
        self._reset_btn.setStyleSheet(f"""
            QPushButton#resetIconThemes {{
                background-color: {c.scrollbar};
                border: none;
                border-radius: 10px;
                color: {c.error};
                font-size: 15px;
                font-weight: 600;
                padding: 12px;
            }}
            QPushButton#resetIconThemes:hover {{ background-color: {c.surface_hover}; }}
        """)
        if getattr(self, "_ios18_table", None) is not None:
            self._ios18_header.setStyleSheet(
                f"color: {c.text_primary}; font-size: 15px;"
                " font-weight: 700; background-color: transparent;")
            self._ios18_hint.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 13px;"
                " background-color: transparent;")
            self._ios18_add_all_btn.setStyleSheet(f"""
                QPushButton#ios18AddAll {{
                    background-color: {c.bg_secondary};
                    border: 1px solid {c.border};
                    border-radius: 12px;
                    color: {c.accent};
                    font-size: 14px;
                    font-weight: 600;
                    padding: 12px;
                }}
                QPushButton#ios18AddAll:hover {{ background-color: {c.surface_hover}; }}
            """)
            self._ios18_status.setStyleSheet(
                f"color: {c.accent}; font-size: 13px;"
                " background-color: transparent;")
            self._ios18_credit.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 12px;"
                " background-color: transparent;")
            self._ios18_table.setStyleSheet(f"""
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
            for btn in self._ios18_add_buttons:
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
        # Rebuild the theme cards so their hardcoded label colors follow the
        # current palette too.
        if hasattr(self, "_themes_box"):
            self.refresh_themes()

    def refresh_themes(self):
        tweak = tweaks[TweakID.IconThemes]
        themes = tweak.themes
        self.themes_placeholder.setVisible(not themes)
        # clear the box
        while self._themes_box.count():
            item = self._themes_box.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not themes:
            return
        for theme in themes:
            self._themes_box.addWidget(self._create_theme_card(theme))

    def _create_theme_card(self, theme: IconTheme) -> QWidget:
        c = self._c
        card = IOSCard()
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 12, 12, 12)
        row.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(56, 56)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(
            f"background-color: {c.bg_secondary}; border-radius: 12px;")
        pixmap = None
        data = theme.get_icon_data()
        # B18: get_icon_data() returns the actual icon PNG bytes (loading them
        # from disk if needed). The old condition only built a pixmap when
        # `data is None`, so a theme WITH icon data never got a thumbnail and
        # always showed "?". Load from the bytes first, fall back to the path.
        if data:
            try:
                candidate = QPixmap()
                if candidate.loadFromData(data):
                    pixmap = candidate
            except Exception:
                pixmap = None
        if (pixmap is None or pixmap.isNull()) and theme.icon_path and os.path.isfile(theme.icon_path):
            try:
                pixmap = QPixmap(theme.icon_path)
            except Exception:
                pixmap = None
        if pixmap is None or pixmap.isNull():
            icon_lbl.setText(QCoreApplication.translate("Nugget", "?"))
        else:
            icon_lbl.setPixmap(pixmap.scaled(
                52, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        row.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        bundle_lbl = QLabel(theme.bundle_id)
        bundle_lbl.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {c.text_primary};")
        bundle_lbl.setWordWrap(True)
        text_col.addWidget(bundle_lbl)
        name_text = theme.display_name if theme.display_name else QCoreApplication.translate("Nugget", "Hide label")
        name_lbl = QLabel(name_text)
        name_lbl.setStyleSheet(f"font-size: 12px; color: {c.text_secondary};")
        name_lbl.setWordWrap(True)
        text_col.addWidget(name_lbl)
        row.addLayout(text_col, 1)

        del_btn = QToolButton()
        del_btn.setIconSize(QSize(18, 18))
        del_btn.setIcon(theme_icon(":/icon/trash.svg", c.text_secondary))
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(
            f"QToolButton {{ background-color: {c.surface_hover}; color: {c.error}; "
            f"border: 1px solid {c.border}; border-radius: 12px; padding: 7px; }}"
            f"QToolButton:hover {{ background-color: {c.error}; color: {c.text_inverse}; }}"
        )
        del_btn.clicked.connect(lambda: self._remove_theme(theme.bundle_id))
        row.addWidget(del_btn)

        return card

    def _remove_theme(self, bundle_id: str):
        tweak = tweaks[TweakID.IconThemes]
        tweak.remove_theme(bundle_id)
        tweak.set_enabled(not tweak.is_empty())
        self.refresh_themes()

    def show_app_list_export(self):
        dialog = AppListExportDialog(self.window)
        if dialog.exec() == QDialog.Accepted:
            app = dialog.selected_app()
            if app is None:
                return
            self.show_add_icon_dialog(bundle_id=app["bundle_id"],
                                      display_name=app["display_name"],
                                      preset=True)

    def show_add_icon_dialog(self, bundle_id: str = "", display_name: str = "",
                             preset: bool = False):
        dialog = IconThemeDialog(self.window, bundle_id=bundle_id,
                                 display_name=display_name, preset=preset)
        if dialog.exec() == QDialog.Accepted:
            theme = dialog.build_theme()
            if theme is None:
                return
            tweak = tweaks[TweakID.IconThemes]
            if not tweak.store_icon(theme):
                QMessageBox.warning(
                    self.window,
                    QCoreApplication.translate("Nugget", "Warning"),
                    QCoreApplication.translate(
                        "Nugget",
                        "Could not store the icon file in the persistent "
                        "folder. The theme may not apply reliably."))
            tweak.add_theme(theme)
            tweak.set_enabled(True)
            self.refresh_themes()

    def show_download_packs(self):
        dialog = IconPackDownloaderDialog(self.window)
        if dialog.exec() == QDialog.Accepted and dialog.added_bundle_ids:
            self.refresh_themes()

    def show_import_pack_zip(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window,
            _tr("Import Icon Pack (.zip)"),
            "",
            "Icon Pack Archives (*.zip)")
        if not path:
            return
        tweak = tweaks[TweakID.IconThemes]
        result = tweak.import_pack_zip_matched(
            path, ios18_pack_hash_index())
        if not result["archive_ok"]:
            QMessageBox.warning(
                self.window,
                _tr("Warning"),
                _tr("That file could not be read as an icon pack (.zip)."))
            return
        imported = result["imported"]
        if imported:
            tweak.set_enabled(True)
            self.refresh_themes()
        summary = _tr("Imported {0} icons from the pack.").format(len(imported))
        self._ios18_status.setText(summary)
        notes = []
        if result["already_present"]:
            notes.append(_tr(
                "{0} icons were already in Icon Themes and were left as "
                "they are.").format(len(result["already_present"])))
        if result["store_failed"]:
            notes.append(_tr(
                "{0} icons could not be stored in the persistent folder; "
                "those themes may not apply reliably.").format(
                    len(result["store_failed"])))
        unmatched = result["unmatched"]
        if unmatched:
            notes.append(_tr(
                "{0} files in the pack did not match any icon in the "
                "built-in 51-app catalog, so they could not be identified "
                "per app and were skipped — no theme was created for "
                "them. They are listed in the details below.").format(
                    len(unmatched)))
        box = QMessageBox(self.window)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(_tr("Icon Pack Import"))
        box.setText(" ".join([summary] + notes))
        if unmatched:
            box.setDetailedText("\n".join(unmatched))
        box.exec()


class IconThemeDialog(QDialog):
    """Pick an app bundle id, an icon image and an optional label."""

    def __init__(self, parent=None, bundle_id: str = "",
                 display_name: str = "", preset: bool = False):
        super().__init__(parent)
        self.setWindowTitle(QCoreApplication.translate("Nugget", "Add Icon Theme"))
        self.setModal(True)
        self.setMinimumWidth(380)
        self._icon_path = ""
        self._retheme()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        bundle_row = QHBoxLayout()
        bundle_row.setSpacing(8)
        bundle_lbl = QLabel(QCoreApplication.translate("Nugget", "App Bundle ID"))
        bundle_lbl.setObjectName("fieldLbl")
        bundle_row.addWidget(bundle_lbl)
        self.bundle_input = QLineEdit()
        self.bundle_input.setObjectName("fieldInput")
        self.bundle_input.setPlaceholderText("com.apple.mobilesafari")
        if bundle_id:
            self.bundle_input.setText(bundle_id)
            if preset:
                self.bundle_input.setReadOnly(True)
        bundle_row.addWidget(self.bundle_input, 1)
        layout.addLayout(bundle_row)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_lbl = QLabel(QCoreApplication.translate("Nugget", "Label"))
        name_lbl.setObjectName("fieldLbl")
        name_row.addWidget(name_lbl)
        self.name_input = QLineEdit()
        self.name_input.setObjectName("fieldInput")
        self.name_input.setPlaceholderText(QCoreApplication.translate(
            "Nugget", "Custom label (empty hides it)"))
        if preset and display_name:
            self.name_input.setText(display_name)
        name_row.addWidget(self.name_input, 1)
        layout.addLayout(name_row)

        hint = QLabel(QCoreApplication.translate(
            "Nugget",
            "The app bundle id is the same identifier the app icon uses "
            "under the hood (e.g. com.instagram.instagram)."))
        if preset:
            hint.setText(QCoreApplication.translate(
                "Nugget",
                "Picked from your iPhone: {0}. Type a custom label or "
                "leave it empty to hide it.").format(bundle_id))
        hint.setObjectName("fieldHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.icon_row = QHBoxLayout()
        self.icon_row.setSpacing(8)
        icon_lbl = QLabel(QCoreApplication.translate("Nugget", "Icon"))
        icon_lbl.setObjectName("fieldLbl")
        self.icon_row.addWidget(icon_lbl)
        self.icon_btn = QPushButton(QCoreApplication.translate("Nugget", "Choose Image (.png)"))
        self.icon_btn.setObjectName("fieldInput")
        self.icon_btn.setCursor(Qt.PointingHandCursor)
        self.icon_btn.clicked.connect(self._choose_icon)
        self.icon_row.addWidget(self.icon_btn, 1)
        layout.addLayout(self.icon_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _retheme(self):
        c = ColorThemeManager.instance().colors
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c.bg_elevated}; }}
            QLabel[objectName="fieldLbl"] {{ color: {c.text_secondary}; font-size: 13px; }}
            QLabel[objectName="fieldHint"] {{ color: {c.text_secondary}; font-size: 12px; }}
            QLineEdit, QPushButton[objectName="fieldInput"] {{
                background-color: {c.bg_input};
                border: none;
                border-radius: 10px;
                color: {c.text_primary};
                font-size: 14px;
                padding: 10px 12px;
            }}
            QPushButton[objectName="fieldInput"]:hover {{ background-color: {c.surface_hover}; }}
            QPushButton {{
                background-color: {c.accent};
                border-radius: 10px;
                color: {c.text_inverse};
                font-size: 14px;
                padding: 10px 20px;
                border: none;
            }}
            QPushButton:hover {{ background-color: {c.accent_hover}; }}
            QPushButton[text="Cancel"] {{ background-color: {c.surface_hover}; color: {c.text_primary}; }}
        """)

    def _choose_icon(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            QCoreApplication.translate("Nugget", "Select Icon Image"),
            "",
            "Images (*.png *.heic *.jpg *.webp)")
        if path:
            self._icon_path = path
            self.icon_btn.setText(os.path.basename(path))

    def _on_accept(self):
        if not self.bundle_input.text().strip():
            QMessageBox.warning(
                self,
                QCoreApplication.translate("Nugget", "Warning"),
                QCoreApplication.translate("Nugget", "Enter the app bundle id."))
            return
        if not self._icon_path:
            QMessageBox.warning(
                self,
                QCoreApplication.translate("Nugget", "Warning"),
                QCoreApplication.translate("Nugget", "Choose an icon image first."))
            return
        self.accept()

    def build_theme(self):
        return IconTheme(
            bundle_id=self.bundle_input.text().strip(),
            display_name=self.name_input.text().strip(),
            icon_path=self._icon_path)