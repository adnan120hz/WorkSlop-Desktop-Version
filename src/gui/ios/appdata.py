"""WorkSlop Desktop App Data page: iMazing-style app container browser.

Real implementation, no facade:
- Lists installed apps via installation_proxy (same as iMazing's app list).
- Browses app data via house_arrest (the same Apple service iMazing uses):
  - VendContainer: full app container (development apps, sideloaded apps)
  - VendDocuments: Documents folder only (apps with iTunes File Sharing)
- Download files from device to computer (AFC pull).
- Upload files from computer to app container (AFC push).

Honest limits (same as iMazing):
- App Store apps without File Sharing: container not accessible (Apple restriction).
- The UI clearly shows which access level each app grants.
"""

import os

from PySide6.QtCore import Qt, QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFileDialog,
    QMessageBox, QListWidget, QListWidgetItem, QPushButton, QSplitter,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QProgressBar,
)

from src.gui.ios.components import IOSCard, IOSPrimaryButton, IOSSectionHeader
from src.gui.theme import t, ColorThemeManager


def tr(text: str) -> str:
    return QCoreApplication.translate("Nugget", text)


class _AppListThread(QThread):
    """Fetch installed apps in background."""
    done = Signal(list)
    error = Signal(str)

    def __init__(self, udid: str):
        super().__init__()
        self.udid = udid

    def run(self):
        try:
            import asyncio
            apps = asyncio.run(self._fetch())
            self.done.emit(apps)
        except Exception as e:
            self.error.emit(str(e))

    async def _fetch(self) -> list:
        from src.devicemanagement.session import lockdown_session
        from pymobiledevice3.services.installation_proxy import InstallationProxyService
        async with lockdown_session(self.udid) as lockdown:
            async with InstallationProxyService(lockdown=lockdown) as ip:
                raw = await ip.get_apps(application_type="Any", calculate_sizes=False)
        apps = []
        for bundle_id, info in (raw or {}).items():
            if not bundle_id:
                continue
            # Skip system apps (no container access anyway)
            app_type = info.get("ApplicationType", "")
            name = (info.get("CFBundleDisplayName")
                    or info.get("CFBundleName") or bundle_id)
            apps.append({
                "bundle_id": bundle_id,
                "display_name": name,
                "version": info.get("CFBundleVersion", ""),
                "app_type": app_type,
                "file_sharing": bool(info.get("UIFileSharingEnabled")),
            })
        apps.sort(key=lambda a: a["display_name"].lower())
        return apps


class _BrowseThread(QThread):
    """Browse app container via house_arrest in background."""
    done = Signal(str, list, str)  # bundle_id, entries, access_level
    error = Signal(str, str)  # bundle_id, error

    def __init__(self, udid: str, bundle_id: str, path: str = ""):
        super().__init__()
        self.udid = udid
        self.bundle_id = bundle_id
        self.path = path

    def run(self):
        try:
            import asyncio
            entries, access = asyncio.run(self._browse())
            self.done.emit(self.bundle_id, entries, access)
        except Exception as e:
            self.error.emit(self.bundle_id, str(e))

    async def _browse(self):
        from src.devicemanagement.session import lockdown_session
        from pymobiledevice3.services.house_arrest import HouseArrestService
        async with lockdown_session(self.udid) as lockdown:
            async with HouseArrestService(lockdown=lockdown) as ha:
                # Try full container first, fall back to Documents
                access = "container"
                try:
                    await ha.send_command(self.bundle_id, "VendContainer")
                except Exception:
                    await ha.send_command(self.bundle_id, "VendDocuments")
                    access = "documents"
                entries = []
                for name in await ha.listdir(self.path or "/"):
                    full = f"{self.path}/{name}".replace("//", "/")
                    try:
                        is_dir = await ha.isdir(full)
                    except Exception:
                        is_dir = False
                    entries.append({"name": name, "is_dir": is_dir, "path": full})
                entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
                return entries, access


class _TransferThread(QThread):
    """Download (pull) or upload (push) files via house_arrest."""
    done = Signal(str)
    error = Signal(str)
    progress = Signal(int, int)

    def __init__(self, udid: str, bundle_id: str, remote_path: str,
                 local_path: str, direction: str):
        super().__init__()
        self.udid = udid
        self.bundle_id = bundle_id
        self.remote_path = remote_path
        self.local_path = local_path
        self.direction = direction  # "pull" or "push"

    def run(self):
        try:
            import asyncio
            asyncio.run(self._transfer())
            self.done.emit(self.local_path)
        except Exception as e:
            self.error.emit(str(e))

    async def _transfer(self):
        from src.devicemanagement.session import lockdown_session
        from pymobiledevice3.services.house_arrest import HouseArrestService
        async with lockdown_session(self.udid) as lockdown:
            async with HouseArrestService(lockdown=lockdown) as ha:
                try:
                    await ha.send_command(self.bundle_id, "VendContainer")
                except Exception:
                    await ha.send_command(self.bundle_id, "VendDocuments")
                if self.direction == "pull":
                    await ha.pull(self.remote_path, self.local_path)
                else:
                    await ha.push(self.local_path, self.remote_path)


class IOSAppDataPage(QWidget):
    """iMazing-style app data browser."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")
        self._c = ColorThemeManager.instance().colors
        self._current_app = None
        self._current_path = ""
        self._access_level = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(t("scroll_area"))
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Info card
        info = IOSCard()
        info_layout = QVBoxLayout(info)
        info_lbl = QLabel(tr(
            "Browse app containers like iMazing. Select an app to see its data. "
            "Full container access works for sideloaded/development apps; "
            "App Store apps only expose Documents if they enable File Sharing."
        ))
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet(f"color: {self._c.text_secondary}; font-size: 13px;")
        info_layout.addWidget(info_lbl)
        layout.addWidget(info)

        # Splitter: apps list | file browser
        splitter = QSplitter(Qt.Horizontal)

        # Left: app list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(IOSSectionHeader(tr("Installed Apps")))
        self.app_list = QListWidget()
        self.app_list.setStyleSheet(t("settings_list"))
        self.app_list.itemClicked.connect(self._on_app_selected)
        left_layout.addWidget(self.app_list, 1)
        self.refresh_btn = IOSPrimaryButton(tr("Refresh Apps"))
        self.refresh_btn.clicked.connect(self.refresh_apps)
        left_layout.addWidget(self.refresh_btn)
        splitter.addWidget(left)

        # Right: file browser
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.path_lbl = QLabel(tr("Select an app to browse its data"))
        self.path_lbl.setStyleSheet(f"color: {self._c.text_primary}; font-size: 14px; font-weight: 600;")
        right_layout.addWidget(self.path_lbl)
        self.access_lbl = QLabel("")
        self.access_lbl.setStyleSheet(f"color: {self._c.text_secondary}; font-size: 12px;")
        right_layout.addWidget(self.access_lbl)

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels([tr("Name"), tr("Type")])
        self.file_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_tree.setStyleSheet(
            f"QTreeWidget {{ background-color: {self._c.bg_primary}; "
            f"color: {self._c.text_primary}; border: 1px solid {self._c.border}; "
            f"border-radius: 8px; font-family: monospace; font-size: 13px; }}"
        )
        self.file_tree.itemDoubleClicked.connect(self._on_file_double_clicked)
        right_layout.addWidget(self.file_tree, 1)

        # Action buttons
        btn_row = QHBoxLayout()
        self.up_btn = QPushButton(tr("↑ Up"))
        self.up_btn.setStyleSheet(t("mini_button"))
        self.up_btn.clicked.connect(self._go_up)
        btn_row.addWidget(self.up_btn)
        self.download_btn = IOSPrimaryButton(tr("Download"))
        self.download_btn.clicked.connect(self._download_selected)
        btn_row.addWidget(self.download_btn)
        self.upload_btn = QPushButton(tr("Upload"))
        self.upload_btn.setStyleSheet(t("mini_button"))
        self.upload_btn.clicked.connect(self._upload_file)
        btn_row.addWidget(self.upload_btn)
        right_layout.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.hide()
        right_layout.addWidget(self.progress)

        splitter.addWidget(right)
        splitter.setSizes([300, 700])
        layout.addWidget(splitter, 1)

        self._threads = []
        self._retheme()

    def _retheme(self):
        pass

    def showEvent(self, event):
        super().showEvent(event)
        if self.app_list.count() == 0:
            self.refresh_apps()

    def _udid(self) -> str:
        try:
            return self.window.device_manager.data_singleton.current_device.udid
        except Exception:
            return ""

    def refresh_apps(self):
        udid = self._udid()
        if not udid:
            QMessageBox.warning(self, tr("App Data"), tr("No device connected."))
            return
        self.app_list.clear()
        self.app_list.addItem(tr("Loading apps..."))
        th = _AppListThread(udid)
        th.done.connect(self._on_apps_loaded)
        th.error.connect(lambda e: QMessageBox.warning(self, tr("App Data"), e))
        th.start()
        self._threads.append(th)

    def _on_apps_loaded(self, apps: list):
        self.app_list.clear()
        for app in apps:
            label = app["display_name"]
            if app["version"]:
                label += f" ({app['version']})"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, app)
            # Mark file-sharing apps
            if app["file_sharing"]:
                item.setToolTip(tr("File Sharing enabled — Documents accessible"))
            self.app_list.addItem(item)

    def _on_app_selected(self, item: QListWidgetItem):
        app = item.data(Qt.UserRole)
        if not app:
            return
        self._current_app = app
        self._current_path = ""
        self._browse(app["bundle_id"], "")

    def _browse(self, bundle_id: str, path: str):
        udid = self._udid()
        if not udid:
            return
        self.path_lbl.setText(f"{bundle_id}:{path or '/'}")
        self.file_tree.clear()
        th = _BrowseThread(udid, bundle_id, path)
        th.done.connect(self._on_browse_done)
        th.error.connect(self._on_browse_error)
        th.start()
        self._threads.append(th)

    def _on_browse_done(self, bundle_id: str, entries: list, access: str):
        if not self._current_app or self._current_app["bundle_id"] != bundle_id:
            return
        self._access_level = access
        self.access_lbl.setText(
            tr("Full container access") if access == "container"
            else tr("Documents only (File Sharing)")
        )
        self.file_tree.clear()
        for e in entries:
            item = QTreeWidgetItem([e["name"], tr("Folder") if e["is_dir"] else tr("File")])
            item.setData(0, Qt.UserRole, e)
            self.file_tree.addTopLevelItem(item)

    def _on_browse_error(self, bundle_id: str, error: str):
        QMessageBox.warning(
            self, tr("App Data"),
            tr(f"Cannot access {bundle_id}: {error}\n\n"
               "This app does not allow container access (Apple restriction).")
        )

    def _on_file_double_clicked(self, item: QTreeWidgetItem, col: int):
        e = item.data(0, Qt.UserRole)
        if e and e["is_dir"] and self._current_app:
            self._current_path = e["path"]
            self._browse(self._current_app["bundle_id"], self._current_path)

    def _go_up(self):
        if not self._current_app or not self._current_path:
            return
        parent = "/".join(self._current_path.rstrip("/").split("/")[:-1])
        self._current_path = parent
        self._browse(self._current_app["bundle_id"], parent)

    def _download_selected(self):
        item = self.file_tree.currentItem()
        if not item or not self._current_app:
            QMessageBox.information(self, tr("App Data"), tr("Select a file first."))
            return
        e = item.data(0, Qt.UserRole)
        if not e or e["is_dir"]:
            QMessageBox.information(self, tr("App Data"), tr("Select a file, not a folder."))
            return
        local = QFileDialog.getSaveFileName(self, tr("Save file"), e["name"])[0]
        if not local:
            return
        self.progress.show()
        th = _TransferThread(
            self._udid(), self._current_app["bundle_id"],
            e["path"], local, "pull",
        )
        th.done.connect(lambda p: (self.progress.hide(),
                                   QMessageBox.information(self, tr("App Data"), tr(f"Saved to {p}"))))
        th.error.connect(lambda err: (self.progress.hide(),
                                      QMessageBox.warning(self, tr("App Data"), err)))
        th.start()
        self._threads.append(th)

    def _upload_file(self):
        if not self._current_app:
            QMessageBox.information(self, tr("App Data"), tr("Select an app first."))
            return
        local = QFileDialog.getOpenFileName(self, tr("Choose file to upload"))[0]
        if not local:
            return
        name = os.path.basename(local)
        remote = f"{self._current_path}/{name}".replace("//", "/")
        self.progress.show()
        th = _TransferThread(
            self._udid(), self._current_app["bundle_id"],
            remote, local, "push",
        )
        th.done.connect(lambda p: (self.progress.hide(),
                                   self._browse(self._current_app["bundle_id"], self._current_path)))
        th.error.connect(lambda err: (self.progress.hide(),
                                      QMessageBox.warning(self, tr("App Data"), err)))
        th.start()
        self._threads.append(th)
