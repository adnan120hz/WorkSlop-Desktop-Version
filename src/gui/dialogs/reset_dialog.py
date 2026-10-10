import logging

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QCheckBox, QVBoxLayout, QSizePolicy

from src.gui.pages.pages_list import Page, get_resettable_pages

logger = logging.getLogger("WorkSlop.reset_dialog")

# Remove options for the v15 firmware-research keys. These are NOT
# page resets and NOT registry specs: each one stages a single
# key = false write into the exact file the v15 enable switch wrote
# (device_manager._reset_tweaks owns the payload). They are always
# offered here because a stray force-fallback key must be removable
# even after its enable switch is gone from the product (v15.1).
from src.devicemanagement.constants import (
    REMOVE_SOLARIUM_SWIFTUI, REMOVE_SOLARIUM_UIKIT)

class ResetDialog(QDialog):
    def __init__(self, device_manager, apply_reset=lambda pages, remove_options=None: None, parent=None):
        super().__init__(parent)
        self.device_manager = device_manager
        self.apply_reset = apply_reset
        self.selected_pages: list[Page] = []
        self.selected_remove_options: list[str] = []

        QBtn = (
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.setWindowTitle(self.tr("Reset Page Tweaks"))

        layout = QVBoxLayout()
        message = QLabel(self.tr("Select the pages you would like to reset."))
        message.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(message)

        pages = get_resettable_pages(self.device_manager)
        for page in pages:
            pageChk = QCheckBox(page.getPageName())
            pageChk.toggled.connect(lambda checked, p=page: self.toggle_page(checked, p))
            layout.addWidget(pageChk)

        # --- v15 Solarium fallback cleanup (always available) ---
        layout.addWidget(QLabel(self.tr(
            "Solarium fallback keys (added by the v15 beta build):")))
        remove_hint = QLabel(self.tr(
            "Each option below writes its key back to false in the exact "
            "file the v15 switch wrote, so the forced fallback turns off. "
            "Reboot after removing."))
        remove_hint.setWordWrap(True)
        layout.addWidget(remove_hint)
        swiftui_chk = QCheckBox(self.tr("Remove Solarium Fallback (SwiftUI)"))
        swiftui_chk.toggled.connect(
            lambda checked: self.toggle_remove_option(checked, REMOVE_SOLARIUM_SWIFTUI))
        layout.addWidget(swiftui_chk)
        uikit_chk = QCheckBox(self.tr("Remove Solarium Fallback (UIKit)"))
        uikit_chk.toggled.connect(
            lambda checked: self.toggle_remove_option(checked, REMOVE_SOLARIUM_UIKIT))
        layout.addWidget(uikit_chk)

        layout.addWidget(self.buttonBox)
        self.setLayout(layout)

    def toggle_page(self, checked: bool, page: Page):
        if checked:
            self.selected_pages.append(page)
        else:
            try:
                self.selected_pages.remove(page)
            except Exception:
                logger.debug("Page not found in list, ignoring error.")

    def toggle_remove_option(self, checked: bool, option: str):
        if checked:
            if option not in self.selected_remove_options:
                self.selected_remove_options.append(option)
        elif option in self.selected_remove_options:
            self.selected_remove_options.remove(option)

    def accept(self):
        super().accept()
        if len(self.selected_pages) > 0 or len(self.selected_remove_options) > 0:
            self.apply_reset(self.selected_pages, self.selected_remove_options)
        # otherwise, ignore
