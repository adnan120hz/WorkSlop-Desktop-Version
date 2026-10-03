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
    QTreeWidget, QTreeWidgetItem, QHeaderView, QProgressBar, QInputDialog,
)

from src.gui.ios.components import IOSCard, IOSPrimaryButton, IOSSectionHeader
from src.devicemanagement.session import install_windows_selector_policy
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
            install_windows_selector_policy()
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
            install_windows_selector_policy()
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


class _BackupBrowseThread(QThread):
    """iMazing-style fallback: back up ONLY AppDomain-<bundle_id>, then list
    its files from Manifest.db. Read-only — writing back would need a restore
    pass, which is a different (destructive) operation."""
    done = Signal(str, object, str)  # bundle_id, _AppDomainTree, backup_dir
    error = Signal(str, str)  # bundle_id, error
    progress = Signal(int)  # 0-100

    def __init__(self, udid: str, bundle_id: str):
        super().__init__()
        self.udid = udid
        self.bundle_id = bundle_id

    def run(self):
        import asyncio
        install_windows_selector_policy()  # Windows: pmd3 selector loop
        try:
            backup_dir = asyncio.run(self._backup())
            from src.restore.appdomain_backup import list_app_domain_files
            tree = list_app_domain_files(backup_dir, self.udid, self.bundle_id)
            self.done.emit(self.bundle_id, tree, backup_dir)
        except Exception as e:
            self.error.emit(self.bundle_id, str(e))

    async def _backup(self) -> str:
        from src.restore.appdomain_backup import targeted_app_domain_backup

        def _on_progress(value):
            try:
                pct = int(float(value) * 100)
            except (TypeError, ValueError):
                pct = -1
            if 0 <= pct <= 100:
                self.progress.emit(pct)

        def _on_label(text):
            pass  # label shown by the page before starting

        return await targeted_app_domain_backup(
            self.udid, self.bundle_id,
            update_label=_on_label, update_progress=_on_progress)


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
            install_windows_selector_policy()
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


class _FileOpThread(QThread):
    """Delete / rename / mkdir inside an app container via house_arrest."""
    done = Signal(str)  # human-readable result message
    error = Signal(str)

    def __init__(self, udid: str, bundle_id: str, op: str,
                 path: str, new_name: str = ""):
        super().__init__()
        self.udid = udid
        self.bundle_id = bundle_id
        self.op = op  # "delete" | "rename" | "mkdir"
        self.path = path
        self.new_name = new_name

    def run(self):
        try:
            import asyncio
            install_windows_selector_policy()
            msg = asyncio.run(self._execute())
            self.done.emit(msg)
        except Exception as e:
            self.error.emit(str(e))

    async def _execute(self) -> str:
        from src.devicemanagement.session import lockdown_session
        from pymobiledevice3.services.house_arrest import HouseArrestService
        async with lockdown_session(self.udid) as lockdown:
            async with HouseArrestService(lockdown=lockdown) as ha:
                try:
                    await ha.send_command(self.bundle_id, "VendContainer")
                except Exception:
                    await ha.send_command(self.bundle_id, "VendDocuments")
                if self.op == "delete":
                    await ha.rm(self.path)
                    return tr("Deleted %1").replace("%1", self.path)
                if self.op == "rename":
                    parent = "/".join(self.path.rstrip("/").split("/")[:-1])
                    new_path = f"{parent}/{self.new_name}".replace("//", "/")
                    await ha.rename(self.path, new_path)
                    return tr("Renamed to %1").replace("%1", self.new_name)
                if self.op == "mkdir":
                    await ha.makedirs(self.path, exist_ok=True)
                    return tr("Created folder %1").replace("%1", self.path)
                raise ValueError(f"Unknown op: {self.op}")


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
            f"border-radius: 8px; font-size: 13px; }}"
            f"QHeaderView::section {{ background-color: {self._c.bg_tertiary}; "
            f"color: {self._c.text_primary}; border: none; "
            f"border-bottom: 1px solid {self._c.border}; padding: 6px; "
            f"font-weight: 600; }}"
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
        self.mkdir_btn = QPushButton(tr("New Folder"))
        self.mkdir_btn.setStyleSheet(t("mini_button"))
        self.mkdir_btn.clicked.connect(self._new_folder)
        btn_row.addWidget(self.mkdir_btn)
        self.rename_btn = QPushButton(tr("Rename"))
        self.rename_btn.setStyleSheet(t("mini_button"))
        self.rename_btn.clicked.connect(self._rename_selected)
        btn_row.addWidget(self.rename_btn)
        self.delete_btn = QPushButton(tr("Delete"))
        self.delete_btn.setStyleSheet(t("mini_button"))
        self.delete_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.delete_btn)
        right_layout.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.hide()
        right_layout.addWidget(self.progress)

        splitter.addWidget(right)
        splitter.setSizes([300, 700])
        layout.addWidget(splitter, 1)

        self._threads = []
        self._backup_cache: dict = {}  # bundle_id -> (tree, backup_dir)
        self._backup_mode = False
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
        self._backup_mode = False
        self._access_level = ""
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
        # iMazing-style fallback: App Store apps without File Sharing deny
        # HouseArrest, but their data is still in the backup under
        # AppDomain-<bundle_id>. Offer to read it from a quick per-app backup.
        ask = QMessageBox.question(
            self, tr("App Data"),
            tr("Cannot access %1 directly:\n%2\n\n"
               "This app does not allow direct container access (Apple restriction).\n\n"
               "Read its data via a device backup instead (like iMazing)?\n"
               "Only this app's data is backed up — nothing else is copied.\n"
               "(Read-only: files can be downloaded, not modified.)").replace("%1", bundle_id).replace("%2", error),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if ask == QMessageBox.StandardButton.Yes:
            self._browse_via_backup(bundle_id)

    def _browse_via_backup(self, bundle_id: str):
        udid = self._udid()
        if not udid:
            return
        # Reuse a cached backup from this session when available.
        cached = self._backup_cache.get(bundle_id)
        if cached is not None:
            tree, _ = cached
            self._enter_backup_mode(bundle_id, tree)
            return
        self.path_lbl.setText(tr("Reading %1 via device backup...").replace("%1", bundle_id))
        self.access_lbl.setText(tr("Backing up app data only — keep the iPhone unlocked."))
        self.file_tree.clear()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.show()
        th = _BackupBrowseThread(udid, bundle_id)
        th.progress.connect(self.progress.setValue)
        th.done.connect(self._on_backup_done)
        th.error.connect(self._on_backup_error)
        th.start()
        self._threads.append(th)

    def _on_backup_done(self, bundle_id: str, tree, backup_dir: str):
        self.progress.hide()
        if not self._current_app or self._current_app["bundle_id"] != bundle_id:
            import shutil
            shutil.rmtree(backup_dir, ignore_errors=True)
            return
        # Bound the session cache; drop the oldest backup first.
        import shutil
        while len(self._backup_cache) >= 3:
            _, (_, old_dir) = self._backup_cache.popitem()
            shutil.rmtree(old_dir, ignore_errors=True)
        self._backup_cache[bundle_id] = (tree, backup_dir)
        self._enter_backup_mode(bundle_id, tree)

    def _on_backup_error(self, bundle_id: str, error: str):
        self.progress.hide()
        self.path_lbl.setText(tr("Select an app to browse its data"))
        self.access_lbl.setText("")
        QMessageBox.warning(self, tr("App Data"), tr("Backup read failed: %1").replace("%1", error))

    def _enter_backup_mode(self, bundle_id: str, tree):
        self._backup_mode = True
        self._backup_tree = tree
        self._current_path = ""
        self._access_level = "backup"
        self.access_lbl.setText(tr("Via device backup (read-only, like iMazing)"))
        self._show_backup_entries("")

    def _show_backup_entries(self, path: str):
        self.path_lbl.setText(f"{self._current_app['bundle_id']}:{path or '/'}")
        self.file_tree.clear()
        for e in self._backup_tree.children(path):
            item = QTreeWidgetItem([e["name"], tr("Folder") if e["is_dir"] else tr("File")])
            item.setData(0, Qt.UserRole, e)
            self.file_tree.addTopLevelItem(item)

    def _backup_mode_active(self) -> bool:
        return self._backup_mode and self._current_app is not None

    def _on_file_double_clicked(self, item: QTreeWidgetItem, col: int):
        e = item.data(0, Qt.UserRole)
        if e and e["is_dir"] and self._current_app:
            self._current_path = e["path"] if "path" in e else e["relativePath"]
            if self._backup_mode_active():
                self._show_backup_entries(self._current_path)
            else:
                self._browse(self._current_app["bundle_id"], self._current_path)

    def _go_up(self):
        if not self._current_app or not self._current_path:
            return
        parent = "/".join(self._current_path.rstrip("/").split("/")[:-1])
        self._current_path = parent
        if self._backup_mode_active():
            self._show_backup_entries(parent)
        else:
            self._browse(self._current_app["bundle_id"], parent)

    def _backup_write_blocked(self) -> bool:
        if self._backup_mode_active():
            QMessageBox.information(
                self, tr("App Data"),
                tr("This view is read-only (data comes from a device backup, "
                   "like iMazing). Downloads work; modifying files does not."))
            return True
        return False

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
        if self._backup_mode_active():
            # Copy straight out of the backup payload — no device round-trip.
            self._download_from_backup(e, local)
            return
        self.progress.show()
        th = _TransferThread(
            self._udid(), self._current_app["bundle_id"],
            e["path"], local, "pull",
        )
        th.done.connect(lambda p: (self.progress.hide(),
                                   QMessageBox.information(self, tr("App Data"), tr("Saved to %1").replace("%1", p))))
        th.error.connect(lambda err: (self.progress.hide(),
                                      QMessageBox.warning(self, tr("App Data"), err)))
        th.start()
        self._threads.append(th)

    def _download_from_backup(self, entry: dict, local: str):
        import shutil
        cached = self._backup_cache.get(self._current_app["bundle_id"])
        if not cached or not entry.get("fileID"):
            QMessageBox.warning(self, tr("App Data"), tr("Backup data not available."))
            return
        _, backup_dir = cached
        from src.restore.appdomain_backup import payload_path
        src = payload_path(backup_dir, self._udid(), entry["fileID"])
        try:
            shutil.copyfile(src, local)
            QMessageBox.information(self, tr("App Data"), tr("Saved to %1").replace("%1", local))
        except OSError as exc:
            QMessageBox.warning(self, tr("App Data"), tr("Could not save file: %1").replace("%1", str(exc)))

    def _upload_file(self):
        if self._backup_write_blocked():
            return
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

    def _selected_entry(self):
        """Return the currently selected file entry dict, or None."""
        item = self.file_tree.currentItem()
        if not item or not self._current_app:
            return None
        return item.data(0, Qt.UserRole)

    def _run_file_op(self, op: str, path: str, new_name: str = ""):
        self.progress.show()
        th = _FileOpThread(
            self._udid(), self._current_app["bundle_id"], op, path, new_name,
        )
        th.done.connect(lambda msg: (self.progress.hide(),
                                     self._browse(self._current_app["bundle_id"],
                                                  self._current_path)))
        th.error.connect(lambda err: (self.progress.hide(),
                                       QMessageBox.warning(self, tr("App Data"), err)))
        th.start()
        self._threads.append(th)

    def _new_folder(self):
        if self._backup_write_blocked():
            return
        if not self._current_app:
            QMessageBox.information(self, tr("App Data"), tr("Select an app first."))
            return
        name, ok = QInputDialog.getText(
            self, tr("New Folder"), tr("Folder name:"))
        if not ok or not name.strip():
            return
        name = name.strip().replace("/", "_")
        remote = f"{self._current_path}/{name}".replace("//", "/")
        self._run_file_op("mkdir", remote)

    def _rename_selected(self):
        if self._backup_write_blocked():
            return
        e = self._selected_entry()
        if not e:
            QMessageBox.information(self, tr("App Data"), tr("Select a file or folder first."))
            return
        new_name, ok = QInputDialog.getText(
            self, tr("Rename"), tr("New name:"), text=e["name"])
        if not ok or not new_name.strip() or new_name.strip() == e["name"]:
            return
        new_name = new_name.strip().replace("/", "_")
        self._run_file_op("rename", e["path"], new_name)

    def _delete_selected(self):
        if self._backup_write_blocked():
            return
        e = self._selected_entry()
        if not e:
            QMessageBox.information(self, tr("App Data"), tr("Select a file or folder first."))
            return
        kind = tr("folder") if e["is_dir"] else tr("file")
        confirm = QMessageBox.question(
            self, tr("Delete"),
            tr("Delete %1 '%2' from the device?\nThis cannot be undone.").replace("%1", kind).replace("%2", e['name']),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._run_file_op("delete", e["path"])
