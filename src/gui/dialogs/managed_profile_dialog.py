"""Dialog: experimental generator for a FeatureFlags .mobileconfig profile.

Honest UI by design (English, plain language):
- EXPERIMENTAL / UNTESTED — effect on a retail iPhone NOT proven.
- Firmware research shows the isAllowedToWriteFeatureFlags gate exists and
  is intact on iOS 26.6.1, so installation will likely be REJECTED on an
  ordinary device. That expected rejection is stated, not hidden.
- Only the PayloadType (com.apple.system.featureflags) and the payload key
  names come from verified firmware binary strings; their value semantics
  are untested and labelled as such.
- No silent install: the user installs the profile manually in Settings.
"""

import logging
import os

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

from src.devicemanagement import managed_profile as mp

logger = logging.getLogger("WorkSlop.managed_profile_dialog")

EXPERIMENTAL_NOTICE = (
    "EXPERIMENTAL — UNTESTED. This generates a .mobileconfig configuration "
    "profile carrying a FeatureFlags payload (PayloadType "
    "'com.apple.system.featureflags', found in iOS firmware).\n\n"
    "The effect on a retail iPhone is NOT proven. Firmware research shows "
    "the isAllowedToWriteFeatureFlags gate exists and is intact on iOS 26.6.1, "
    "so installation will likely be REJECTED on an ordinary (non-supervised, "
    "non-MDM) device. If iOS refuses the profile, that is the expected "
    "outcome there — not a bug in this generator.\n\n"
    "The payload key names (Features / Domain / FeatureName / Enabled / "
    "Disclosures / Subscriptions) come from firmware binary strings; their "
    "exact value semantics on a device are untested. Nothing is installed "
    "silently — you install the profile yourself in Settings."
)


class _FeatureRow(QWidget):
    def __init__(self, parent=None, on_remove=None):
        super().__init__(parent)
        self._on_remove = on_remove
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.domain_edit = QLineEdit(self)
        self.domain_edit.setPlaceholderText("Domain (e.g. com.apple.UIKit)")
        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText("FeatureName")
        self.enabled_chk = QCheckBox("Enabled", self)
        self.enabled_chk.setChecked(True)
        rm = QPushButton("Remove", self)
        rm.clicked.connect(self._remove)
        lay.addWidget(self.domain_edit, 3)
        lay.addWidget(self.name_edit, 3)
        lay.addWidget(self.enabled_chk, 1)
        lay.addWidget(rm, 1)

    def _remove(self):
        if self._on_remove:
            self._on_remove(self)

    def entry(self) -> dict:
        return {
            "Domain": self.domain_edit.text().strip(),
            "FeatureName": self.name_edit.text().strip(),
            "Enabled": self.enabled_chk.isChecked(),
        }


class ManagedProfileDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Managed Profile — FeatureFlags (Experimental)")
        self.setMinimumWidth(640)
        self._rows: list[_FeatureRow] = []

        layout = QVBoxLayout(self)

        notice = QLabel(EXPERIMENTAL_NOTICE)
        notice.setWordWrap(True)
        notice.setStyleSheet(
            "background: #FFF7E6; border: 1px solid #E8C547; border-radius: 8px; "
            "padding: 10px; font-size: 13px;")
        layout.addWidget(notice)

        form = QFormLayout()
        self.name_edit = QLineEdit("WorkSlop FeatureFlags (Experimental)")
        self.org_edit = QLineEdit()
        self.org_edit.setPlaceholderText("Optional")
        form.addRow("Profile name:", self.name_edit)
        form.addRow("Organization:", self.org_edit)
        layout.addLayout(form)

        layout.addWidget(QLabel("Feature entries (at least one required):"))
        self.rows_box = QVBoxLayout()
        rows_host = QWidget()
        rows_host.setLayout(self.rows_box)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(rows_host)
        scroll.setMaximumHeight(180)
        layout.addWidget(scroll)

        add_row_btn = QPushButton("Add feature row")
        add_row_btn.clicked.connect(self._add_row)
        layout.addWidget(add_row_btn)
        self._add_row()

        self.status_lbl = QLabel("")
        self.status_lbl.setWordWrap(True)
        layout.addWidget(self.status_lbl)

        self.instructions = QTextEdit()
        self.instructions.setReadOnly(True)
        self.instructions.setPlainText(mp.INSTALL_INSTRUCTIONS)
        self.instructions.setMaximumHeight(190)
        layout.addWidget(QLabel("Install steps:"))
        layout.addWidget(self.instructions)

        btns = QHBoxLayout()
        self.gen_btn = QPushButton("Generate .mobileconfig…")
        self.gen_btn.clicked.connect(self._generate)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btns.addWidget(self.gen_btn)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

    def _add_row(self):
        row = _FeatureRow(on_remove=self._remove_row)
        self._rows.append(row)
        self.rows_box.addWidget(row)

    def _remove_row(self, row):
        if len(self._rows) <= 1:
            return
        self._rows.remove(row)
        self.rows_box.removeWidget(row)
        row.deleteLater()

    def _generate(self):
        features = [r.entry() for r in self._rows]
        errors = mp.validate_feature_entries(features)
        if errors:
            QMessageBox.warning(self, "Invalid input", "\n".join(errors))
            return
        try:
            profile = mp.build_feature_flags_profile(
                self.name_edit.text(), self.org_edit.text(), features)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid input", str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save .mobileconfig profile",
            os.path.expanduser("~/WorkSlop-FeatureFlags.mobileconfig"),
            "Configuration profile (*.mobileconfig)")
        if not path:
            return
        if not path.endswith(".mobileconfig"):
            path += ".mobileconfig"
        try:
            mp.write_mobileconfig(profile, path)
        except OSError as exc:
            logger.error("Failed to write profile: %s", exc)
            QMessageBox.critical(self, "Write failed", str(exc))
            return
        self.status_lbl.setText(
            f"Saved: {path}\n"
            "Next: transfer it to your iPhone, then Settings → "
            "Profile Downloaded → Install manually, reboot, and check.")
        logger.info("Wrote experimental FeatureFlags profile to %s", path)
