"""WorkSlop Desktop Backup page: full backup, restore, and backup location.

The three actions reuse the exact flows already wired in the Settings page —
this page only gives them a dedicated home under the Backup sidebar menu.
"""
from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFileDialog,
    QMessageBox,
)

from src.gui.ios.components import IOSCard, IOSPrimaryButton, IOSSectionHeader
from src.gui.theme import t, ColorThemeManager


def tr(text: str) -> str:
    return QCoreApplication.translate("Nugget", text)


class IOSBackupPage(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")
        self._tm = ColorThemeManager.instance()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        self._scroll = scroll
        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(16, 16, 16, 24)
        self._content_layout.setSpacing(12)

        self._content_layout.addWidget(IOSSectionHeader(tr("Backup")))

        # Safety notice: protective != full.
        self._content_layout.addWidget(self._make_notice_card(
            tr("For maximum safety, use Full Backup"),
            tr("The protective backup below only saves your photos, messages, "
               "contacts, Apple ID / settings data and the keychain — not "
               "everything on the iPhone. If you want to be fully safe before "
               "applying tweaks, run a Full Backup first.")))

        self._content_layout.addWidget(self._make_card(
            tr("Protective Backup"),
            tr("A selective backup of the things the tweak flow needs to "
               "restore: photos, messages, contacts, Apple ID and settings "
               "data, plus the keychain when the device backup is encrypted.\n\n"
               "This is NOT a full backup — app data and the rest of the "
               "iPhone are not included. On iOS 27 this backup runs "
               "automatically before tweaks are applied."),
            tr("Start Protective Backup"),
            self._on_protective_backup))

        self._content_layout.addWidget(self._make_apply_card())

        self._content_layout.addWidget(self._make_card(
            tr("Full Backup"),
            tr("Create a complete backup of the iPhone, the way iTunes/Finder "
               "does. Make sure this computer has enough free storage — the "
               "backup can be as large as the used storage on the iPhone — "
               "and note this takes much longer than the protective backup."),
            tr("Start Full Backup"),
            self._on_full_backup))

        self._content_layout.addWidget(self._make_card(
            tr("Restore Backup"),
            tr("Restore a backup to the iPhone. Two formats are supported: a "
               "standard full-backup folder (iTunes/Finder format), or the "
               "protective backup this app keeps on this computer."),
            tr("Restore..."),
            self._on_restore))

        self._location_lbl = QLabel()
        self._location_lbl.setWordWrap(True)
        self._content_layout.addWidget(self._make_card(
            tr("Backup Location"),
            tr("The protective backup cache and temporary backup/restore "
               "files are stored here. The protective backup runs "
               "automatically before tweaks are applied."),
            tr("Open Folder"),
            self._on_open_location,
            extra_widget=self._location_lbl))

        self._content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._retheme()
        self._tm.theme_changed.connect(self._retheme)

    # -- cards ----------------------------------------------------------
    def _make_card(self, title, desc, btn_text, handler, extra_widget=None):
        card = IOSCard()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        title_lbl = QLabel(tr(title))
        title_lbl.setStyleSheet(
            "font-size: 15px; font-weight: 600; background-color: transparent;")
        lay.addWidget(title_lbl)
        desc_lbl = QLabel(tr(desc))
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(t("value_label") + " background-color: transparent;")
        lay.addWidget(desc_lbl)
        if extra_widget is not None:
            extra_widget.setStyleSheet(
                t("value_label") + " background-color: transparent;")
            lay.addWidget(extra_widget)
        row = QHBoxLayout()
        row.addStretch(1)
        btn = IOSPrimaryButton(tr(btn_text))
        btn.clicked.connect(handler)
        row.addWidget(btn)
        lay.addLayout(row)
        return card

    def _make_notice_card(self, title, desc):
        """Warning-style card for the full-backup safety notice."""
        card = IOSCard()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)
        title_lbl = QLabel("⚠  " + tr(title))
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {self._tm.colors.warning}; "
            "background-color: transparent;")
        lay.addWidget(title_lbl)
        desc_lbl = QLabel(tr(desc))
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(t("value_label") + " background-color: transparent;")
        lay.addWidget(desc_lbl)
        return card

    def _make_apply_card(self):
        """Apply/Remove Tweaks lives here (not a separate sidebar item)."""
        card = IOSCard()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        title_lbl = QLabel(tr("Apply Tweaks"))
        title_lbl.setStyleSheet(
            "font-size: 15px; font-weight: 600; background-color: transparent;")
        lay.addWidget(title_lbl)
        desc_lbl = QLabel(tr(
            "Apply the tweaks you enabled on the other pages.\n\n"
            # HONESTY-AUDIT FIX (#7): the old text described the classic
            # wipe flow as if it always runs. The default merged flow
            # (merge_phases=True) applies tweaks and restores the
            # protective backup in one session WITHOUT wiping. The wipe
            # only happens with GOLDENNUGGET_NO_MERGE_PHASES=1 or when a
            # tweak forces iOS into security-recovery (automatic fallback).
            "On iOS 27 the protective backup runs automatically first, then "
            "the tweaks are applied and your photos / messages / contacts / "
            "settings are put back — normally without wiping the iPhone. "
            "A full wipe-and-restore only runs if a tweak forces iOS into "
            "security recovery.\n\n"
            "On iOS 26 the tweaks apply directly, without a wipe."))
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(t("value_label") + " background-color: transparent;")
        lay.addWidget(desc_lbl)
        row = QHBoxLayout()
        row.addStretch(1)
        self._apply_btn = IOSPrimaryButton(tr("Apply Tweaks"))
        self._apply_btn.clicked.connect(self._on_apply_tweaks)
        row.addWidget(self._apply_btn)
        remove_btn = IOSPrimaryButton(tr("Remove Tweaks"))
        remove_btn.clicked.connect(self._on_remove_tweaks)
        row.addWidget(remove_btn)
        lay.addLayout(row)
        # Status line: explains why Apply is greyed out when nothing is on.
        self._apply_status = QLabel("")
        self._apply_status.setWordWrap(True)
        self._apply_status.setStyleSheet(
            t("value_label") + " background-color: transparent; font-size: 12px;")
        lay.addWidget(self._apply_status)
        return card

    def refresh_apply_state(self):
        """Enable Apply only when at least one tweak toggle is on anywhere.

        Called whenever the Backup page is shown; otherwise the button
        would lie about there being something to apply.
        """
        try:
            _lines, total = self.window._build_apply_summary()
        except Exception:
            total = 0
        has = total > 0
        self._apply_btn.setEnabled(has)
        if has:
            self._apply_status.setText(
                QCoreApplication.translate(
                    "Nugget", "%n tweak(s) enabled — ready to apply.",
                    "", total))
        else:
            self._apply_status.setText(
                tr("Apply is disabled: enable at least one tweak toggle "
                   "on any menu first."))

    # -- actions (same flows as Settings) -------------------------------
    def _on_protective_backup(self):
        reply = QMessageBox.warning(
            self.window, tr("Protective Backup"),
            tr("This creates a SELECTIVE backup: photos, messages, contacts, "
               "Apple ID and settings data, plus the keychain when the "
               "device backup is encrypted.\n\n"
               "It is NOT a full backup. For maximum safety, run a Full "
               "Backup too.\n\n"
               "Continue?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.window._start_protective_backup()

    def _on_apply_tweaks(self):
        self.window.apply_tweaks_clicked()

    def _on_remove_tweaks(self):
        self.window.remove_tweaks_clicked()

    def _on_full_backup(self):
        reply = QMessageBox.warning(
            self.window, tr("Full Backup"),
            tr("This creates a COMPLETE backup of the iPhone, the way "
               "iTunes/Finder does.\n\n"
               "Make sure this computer has enough free storage — the backup "
               "can be as large as the used storage on the iPhone — and note "
               "this takes much longer than the protective backup.\n\n"
               "Continue?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        folder = QFileDialog.getExistingDirectory(
            self.window, tr("Where to save the full backup"), "",
            QFileDialog.Option.ShowDirsOnly)
        if not folder:
            return
        self.window._start_full_backup(folder)

    def _on_restore(self):
        mbox = QMessageBox(self.window)
        mbox.setWindowTitle(tr("Restore Backup"))
        mbox.setText(tr("Choose the backup format to restore:"))
        mbox.setInformativeText(
            tr("Full Backup: a standard iPhone backup folder in iTunes/Finder "
               "format (Manifest.db/Manifest.plist + Info.plist).\n\n"
               "Protective Backup: the selective protective backup this app "
               "keeps on this computer (only restorable from this app)."))
        full_btn = mbox.addButton(tr("Full Backup..."), QMessageBox.ButtonRole.ActionRole)
        prot_btn = mbox.addButton(tr("Protective Backup"), QMessageBox.ButtonRole.ActionRole)
        mbox.addButton(QMessageBox.StandardButton.Cancel)
        mbox.exec()
        clicked = mbox.clickedButton()
        if clicked == full_btn:
            self._on_restore_full()
        elif clicked == prot_btn:
            self._on_restore_protective()

    def _on_restore_full(self):
        folder = QFileDialog.getExistingDirectory(
            self.window, tr("Select Full Backup Folder"), "",
            QFileDialog.Option.ShowDirsOnly)
        if not folder:
            return
        reply = QMessageBox.question(
            self.window, tr("Restore Full Backup?"),
            tr("This restores the selected backup to the connected iPhone, "
               "then reboots it.\n\n"
               "Make sure the iPhone is connected, unlocked and awake, "
               "then do you want to continue?"))
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.window._start_full_backup_restore(folder)

    def _on_restore_protective(self):
        reply = QMessageBox.question(
            self.window, tr("Restore Data From Backup?"),
            tr("This restores photos, messages, contacts and settings from "
               "the last protective backup on this computer.\n\n"
               "Applied tweaks and wallpapers are KEPT.\n\n"
               "Make sure the iPhone is connected, unlocked and awake, "
               "then do you want to continue?"))
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.window._start_cache_restore()

    def _on_open_location(self):
        import os
        path = self._backup_dir()
        if path and os.path.isdir(path):
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # -- helpers --------------------------------------------------------
    def _backup_dir(self) -> str:
        try:
            custom = str(self.window.settings.value("backup_storage_dir", "", type=str)).strip()
            if custom:
                return custom
            from src.restore.storage import cache_base
            return str(cache_base())
        except Exception:
            return ""

    def refresh(self):
        path = self._backup_dir()
        self._location_lbl.setText(path if path else tr("Default (system drive)"))
        self.refresh_apply_state()

    def _retheme(self):
        c = self._tm.colors
        self._scroll.setStyleSheet(
            f"background-color: {c.bg_primary}; border: none;")
        self.refresh()
