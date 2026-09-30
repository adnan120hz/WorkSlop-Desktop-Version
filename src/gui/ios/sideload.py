"""WorkSlop Desktop Sideloading page: Sideloadly-style IPA sideloading.

Real implementation, no facade:
- Apple ID sign-in via Apple GrandSlam (SRP) + locally generated anisette —
  the same flow Sideloadly/AltStore use. Password lives only in memory for
  the login call; only short-lived session tokens are cached on disk.
- IPA inspector: reads name, version, bundle id, icon, encryption and
  extension info straight from the .ipa.
- Sign + install: free Apple ID development certificate, provisioning via
  Apple's developer services, signing via zsign, install via
  installation_proxy — all real, with live progress.
- Manual signing with the user's own .p12 + .mobileprovision.
- Installed-apps list with uninstall, straight from the device.

Engine: ``src.sideload.ipaside_engine`` (MIT, see src/sideload/ATTRIBUTION.md).
"""
import base64
import os

from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFileDialog,
    QMessageBox, QLineEdit, QProgressBar, QInputDialog, QListWidget,
    QListWidgetItem, QCheckBox,
)

from src.gui.ios.components import IOSCard, IOSPrimaryButton, IOSSectionHeader
from src.gui.theme import t, ColorThemeManager
from src.gui.thread_workers.sideload_worker import (
    LoginThread, SideloadThread, InstalledAppsThread, UninstallThread,
)


def tr(text: str) -> str:
    return QCoreApplication.translate("Nugget", text)


class IOSSideloadPage(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")
        self._tm = ColorThemeManager.instance()
        self._ipa_path = None
        self._ipa_info = None
        self._threads = []
        self._login_thread = None

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

        self._content_layout.addWidget(IOSSectionHeader(tr("Sideloading")))

        self._content_layout.addWidget(self._make_notice_card(
            tr("How this works"),
            tr("Sign in with an Apple ID (a spare one is recommended). The app "
               "registers a free development certificate for that Apple ID, "
               "signs the IPA on this computer, and installs it on the iPhone "
               "over USB.\n\n"
               "Apple's free-account limits apply: apps stop opening after "
               "7 days (re-sideload to refresh), max 3 sideloaded apps per "
               "device, and roughly 10 App IDs per 7 days.")))

        self._content_layout.addWidget(self._make_account_card())
        self._content_layout.addWidget(self._make_ipa_card())
        self._content_layout.addWidget(self._make_sideload_card())
        self._content_layout.addWidget(self._make_installed_card())
        self._content_layout.addWidget(self._make_manual_card())

        self._content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        self._retheme()
        self._tm.theme_changed.connect(self._retheme)
        self.refresh_account()

    # -- cards ----------------------------------------------------------
    def _make_notice_card(self, title, desc):
        card = IOSCard()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)
        title_lbl = QLabel(title)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 700; background-color: transparent;")
        lay.addWidget(title_lbl)
        desc_lbl = QLabel(desc)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(t("value_label") + " background-color: transparent;")
        lay.addWidget(desc_lbl)
        return card

    def _make_card_shell(self, title):
        card = IOSCard()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "font-size: 15px; font-weight: 600; background-color: transparent;")
        lay.addWidget(title_lbl)
        return card, lay

    def _make_account_card(self):
        card, lay = self._make_card_shell(tr("Apple ID"))
        self._account_status = QLabel(tr("Not signed in."))
        self._account_status.setWordWrap(True)
        self._account_status.setStyleSheet(
            t("value_label") + " background-color: transparent;")
        lay.addWidget(self._account_status)

        self._email_edit = QLineEdit()
        self._email_edit.setPlaceholderText(tr("Apple ID email"))
        self._email_edit.setClearButtonEnabled(True)
        lay.addWidget(self._email_edit)

        self._pass_edit = QLineEdit()
        self._pass_edit.setPlaceholderText(tr("Password"))
        self._pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pass_edit.setClearButtonEnabled(True)
        lay.addWidget(self._pass_edit)

        row = QHBoxLayout()
        row.addStretch(1)
        self._signin_btn = IOSPrimaryButton(tr("Sign In"))
        self._signin_btn.clicked.connect(self._on_sign_in)
        row.addWidget(self._signin_btn)
        self._signout_btn = IOSPrimaryButton(tr("Sign Out"))
        self._signout_btn.clicked.connect(self._on_sign_out)
        row.addWidget(self._signout_btn)
        lay.addLayout(row)

        note = QLabel(tr(
            "Privacy: your password is used once to sign in and is never "
            "stored anywhere — not in the app, not on disk, not in the repo. "
            "Only short-lived Apple session tokens are kept in a private "
            "per-user folder on this computer (owner-only permissions), "
            "exactly like Sideloadly does. Sign Out wipes them completely. "
            "Your Apple ID never leaves this computer except to Apple's own "
            "servers (gsa.apple.com)."))
        note.setWordWrap(True)
        note.setStyleSheet(t("value_label") + " background-color: transparent;")
        lay.addWidget(note)
        return card

    def _make_ipa_card(self):
        card, lay = self._make_card_shell(tr("IPA File"))
        self._ipa_icon = QLabel()
        self._ipa_icon.setFixedSize(57, 57)
        self._ipa_icon.setAlignment(Qt.AlignCenter)
        self._ipa_label = QLabel(tr("No IPA selected."))
        self._ipa_label.setWordWrap(True)
        self._ipa_label.setStyleSheet(
            t("value_label") + " background-color: transparent;")
        top = QHBoxLayout()
        top.addWidget(self._ipa_icon)
        top.addWidget(self._ipa_label, 1)
        lay.addLayout(top)
        self._ipa_warn = QLabel()
        self._ipa_warn.setWordWrap(True)
        self._ipa_warn.setStyleSheet(
            f"font-size: 13px; color: {self._tm.colors.warning}; background-color: transparent;")
        self._ipa_warn.setVisible(False)
        lay.addWidget(self._ipa_warn)
        row = QHBoxLayout()
        row.addStretch(1)
        pick_btn = IOSPrimaryButton(tr("Choose IPA..."))
        pick_btn.clicked.connect(self._on_choose_ipa)
        row.addWidget(pick_btn)
        lay.addLayout(row)
        return card

    def _make_sideload_card(self):
        card, lay = self._make_card_shell(tr("Sideload to iPhone"))
        desc = QLabel(tr(
            "Signs the selected IPA with your Apple ID's free development "
            "certificate and installs it on the connected iPhone."))
        desc.setWordWrap(True)
        desc.setStyleSheet(t("value_label") + " background-color: transparent;")
        lay.addWidget(desc)

        self._bundle_edit = QLineEdit()
        self._bundle_edit.setPlaceholderText(tr("Custom bundle ID (optional)"))
        self._bundle_edit.setClearButtonEnabled(True)
        lay.addWidget(self._bundle_edit)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(tr("Custom display name (optional)"))
        self._name_edit.setClearButtonEnabled(True)
        lay.addWidget(self._name_edit)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        lay.addWidget(self._progress)
        self._progress_lbl = QLabel()
        self._progress_lbl.setWordWrap(True)
        self._progress_lbl.setStyleSheet(
            t("value_label") + " background-color: transparent;")
        self._progress_lbl.setVisible(False)
        lay.addWidget(self._progress_lbl)

        row = QHBoxLayout()
        row.addStretch(1)
        self._sideload_btn = IOSPrimaryButton(tr("Sideload"))
        self._sideload_btn.clicked.connect(self._on_sideload)
        row.addWidget(self._sideload_btn)
        lay.addLayout(row)
        return card

    def _make_installed_card(self):
        card, lay = self._make_card_shell(tr("Installed Apps"))
        self._apps_list = QListWidget()
        self._apps_list.setMaximumHeight(180)
        lay.addWidget(self._apps_list)
        row = QHBoxLayout()
        row.addStretch(1)
        refresh_btn = IOSPrimaryButton(tr("Refresh"))
        refresh_btn.clicked.connect(self._on_refresh_apps)
        row.addWidget(refresh_btn)
        uninst_btn = IOSPrimaryButton(tr("Uninstall Selected"))
        uninst_btn.clicked.connect(self._on_uninstall)
        row.addWidget(uninst_btn)
        lay.addLayout(row)
        return card

    def _make_manual_card(self):
        card, lay = self._make_card_shell(tr("Manual Signing"))
        desc = QLabel(tr(
            "Already have your own development certificate? Pick the .p12 "
            "and .mobileprovision and sign the IPA without touching an "
            "Apple ID. Needs zsign on PATH (or WORKSLOP_ZSIGN set)."))
        desc.setWordWrap(True)
        desc.setStyleSheet(t("value_label") + " background-color: transparent;")
        lay.addWidget(desc)
        self._p12_path = None
        self._prov_path = None
        self._manual_lbl = QLabel(tr("No certificate selected."))
        self._manual_lbl.setWordWrap(True)
        self._manual_lbl.setStyleSheet(
            t("value_label") + " background-color: transparent;")
        lay.addWidget(self._manual_lbl)
        row = QHBoxLayout()
        row.addStretch(1)
        p12_btn = IOSPrimaryButton(tr(".p12..."))
        p12_btn.clicked.connect(self._on_pick_p12)
        row.addWidget(p12_btn)
        prov_btn = IOSPrimaryButton(tr(".mobileprovision..."))
        prov_btn.clicked.connect(self._on_pick_prov)
        row.addWidget(prov_btn)
        sign_btn = IOSPrimaryButton(tr("Sign Only"))
        sign_btn.clicked.connect(self._on_manual_sign)
        row.addWidget(sign_btn)
        lay.addLayout(row)
        return card

    # -- Apple ID -------------------------------------------------------
    def refresh_account(self):
        try:
            from src.sideload.ipaside_engine import gsa
            state = gsa.status()
            if state.get("authenticated"):
                email = state.get("email", "")
                self._account_status.setText(
                    tr("Signed in as ") + email)
                self._email_edit.setText(email)
                self._email_edit.setEnabled(False)
                self._pass_edit.setEnabled(False)
                self._signin_btn.setEnabled(False)
                self._signout_btn.setEnabled(True)
            else:
                raise RuntimeError("not signed in")
        except Exception:
            self._account_status.setText(tr("Not signed in."))
            self._email_edit.setEnabled(True)
            self._pass_edit.setEnabled(True)
            self._signin_btn.setEnabled(True)
            self._signout_btn.setEnabled(False)

    def _on_sign_in(self):
        email = self._email_edit.text().strip()
        password = self._pass_edit.text()
        if not email or not password:
            QMessageBox.warning(self.window, tr("Apple ID"),
                                tr("Enter your Apple ID email and password."))
            return
        # Clear the visible password field right away; the worker keeps its
        # own copy only for the login call.
        self._pass_edit.clear()
        self._signin_btn.setEnabled(False)
        self._account_status.setText(tr("Signing in..."))
        thread = LoginThread(email, password, self)
        thread.twofa_required.connect(self._on_2fa_required)
        thread.finished_with_result.connect(self._on_login_done)
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        self._login_thread = thread
        thread.start()

    def _on_2fa_required(self, method):
        if method == "sms":
            prompt = tr("Apple sent a verification code by SMS. Enter it:")
        else:
            prompt = tr("Apple sent a verification code to your trusted "
                        "device(s). Enter it:")
        code, ok = QInputDialog.getText(
            self.window, tr("Two-Factor Authentication"), prompt)
        thread = getattr(self, "_login_thread", None)
        if thread is not None:
            if ok and code.strip():
                thread.submit_2fa(code.strip())
            else:
                thread.submit_2fa("")

    def _on_login_done(self, ok, message):
        self._threads = [t for t in self._threads
                         if t is not getattr(self, "_login_thread", None)]
        self._login_thread = None
        if ok:
            QMessageBox.information(self.window, tr("Apple ID"), message)
        else:
            QMessageBox.warning(self.window, tr("Sign In Failed"), message)
        self.refresh_account()

    def _on_sign_out(self):
        try:
            from src.sideload.ipaside_engine import gsa
            email = self._email_edit.text().strip() or None
            gsa.logout(email)
        except Exception as exc:
            QMessageBox.warning(self.window, tr("Sign Out"),
                                tr("Could not sign out: ") + str(exc))
        self.refresh_account()

    # -- IPA ------------------------------------------------------------
    def _on_choose_ipa(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window, tr("Choose IPA"), "",
            tr("iOS Apps (*.ipa)"))
        if not path:
            return
        try:
            from src.sideload.ipaside_engine import ipa
            info = ipa.inspect(path)
        except Exception as exc:
            QMessageBox.warning(self.window, tr("IPA"),
                                tr("Could not read IPA: ") + str(exc))
            return
        self._ipa_path = path
        self._ipa_info = info
        name = info.get("display_name") or info.get("bundle_id") or "?"
        ver = info.get("version") or ""
        build = info.get("build") or ""
        self._ipa_label.setText(
            f"{name}\n{info.get('bundle_id', '')}\n"
            f"v{ver} ({build})  ·  iOS {info.get('minimum_os', '?')}+")
        icon_data = info.get("icon")
        if icon_data:
            # inspect() returns a "data:image/png;base64,..." URI string;
            # QPixmap.loadFromData needs raw bytes, not str.
            raw = icon_data
            if isinstance(raw, str):
                if "," in raw:
                    raw = raw.split(",", 1)[1]
                try:
                    raw = base64.b64decode(raw)
                except Exception:
                    raw = None
            pm = QPixmap()
            if raw and pm.loadFromData(raw):
                self._ipa_icon.setPixmap(pm.scaled(
                    57, 57, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        warns = []
        if info.get("has_sc_info"):
            warns.append(tr("This IPA is App Store encrypted and cannot be "
                            "re-signed — sideloading it will fail."))
        if info.get("extensions"):
            warns.append(tr("Contains %n app extension(s); they will be "
                            "stripped for the free-account install.",
                            "", len(info["extensions"])))
        if info.get("has_watch_app"):
            warns.append(tr("Contains a watch app; it will be stripped."))
        platform = info.get("platform")
        if platform and platform != "ios":
            warns.append(tr("This IPA targets %1, not iPhone.") % platform)
        if warns:
            self._ipa_warn.setText("\n".join("⚠ " + w for w in warns))
            self._ipa_warn.setVisible(True)
        else:
            self._ipa_warn.setVisible(False)

    # -- sideload -------------------------------------------------------
    def _device_udid(self):
        try:
            dev = self.window.dev
            return getattr(dev, "udid", None)
        except Exception:
            return None

    def _on_sideload(self):
        if not self._ipa_path:
            QMessageBox.warning(self.window, tr("Sideload"),
                                tr("Choose an IPA first."))
            return
        udid = self._device_udid()
        if not udid:
            QMessageBox.warning(
                self.window, tr("Sideload"),
                tr("No iPhone connected. Connect it over USB, unlock it and "
                   "tap Trust, then try again."))
            return
        try:
            from src.sideload.ipaside_engine import gsa
            if not gsa.status().get("authenticated"):
                QMessageBox.warning(
                    self.window, tr("Sideload"),
                    tr("Sign in with an Apple ID first — the IPA needs a "
                       "development certificate."))
                return
        except Exception as exc:
            QMessageBox.warning(self.window, tr("Sideload"), str(exc))
            return
        self._sideload_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._progress_lbl.setVisible(True)
        self._progress_lbl.setText(tr("Starting..."))
        bundle_id = self._bundle_edit.text().strip() or None
        display_name = self._name_edit.text().strip() or None
        thread = SideloadThread(self._ipa_path, udid,
                               bundle_id=bundle_id,
                               display_name=display_name,
                               parent=self)
        thread.progress.connect(self._on_sideload_progress)
        thread.finished_with_result.connect(self._on_sideload_done)
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        thread.start()

    def _on_sideload_progress(self, pct, text):
        if pct >= 0:
            self._progress.setValue(min(pct, 100))
        self._progress_lbl.setText(text)

    def _on_sideload_done(self, ok, message):
        self._threads = [t for t in self._threads
                         if not isinstance(t, SideloadThread)]
        self._sideload_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._progress_lbl.setVisible(False)
        if ok:
            QMessageBox.information(self.window, tr("Sideload"), message)
            self._on_refresh_apps()
        else:
            QMessageBox.warning(self.window, tr("Sideload Failed"), message)

    # -- installed apps -------------------------------------------------
    def _on_refresh_apps(self):
        udid = self._device_udid()
        if not udid:
            QMessageBox.warning(self.window, tr("Installed Apps"),
                                tr("No iPhone connected."))
            return
        self._apps_list.clear()
        item = QListWidgetItem(tr("Loading..."))
        item.setFlags(Qt.NoItemFlags)
        self._apps_list.addItem(item)
        thread = InstalledAppsThread(udid, self)
        thread.finished_with_result.connect(self._on_apps_loaded)
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        thread.start()

    def _on_apps_loaded(self, ok, payload):
        self._threads = [t for t in self._threads
                         if not isinstance(t, InstalledAppsThread)]
        self._apps_list.clear()
        if not ok:
            item = QListWidgetItem(tr("Failed: ") + str(payload))
            item.setFlags(Qt.NoItemFlags)
            self._apps_list.addItem(item)
            return
        for app in payload:
            item = QListWidgetItem(
                f"{app['name']}  ({app['version']})\n{app['bundle_id']}")
            item.setData(Qt.UserRole, app["bundle_id"])
            self._apps_list.addItem(item)
        if not payload:
            item = QListWidgetItem(tr("No sideloaded apps found."))
            item.setFlags(Qt.NoItemFlags)
            self._apps_list.addItem(item)

    def _on_uninstall(self):
        item = self._apps_list.currentItem()
        if item is None:
            return
        bundle_id = item.data(Qt.UserRole)
        if not bundle_id:
            return
        reply = QMessageBox.question(
            self.window, tr("Uninstall"),
            tr("Uninstall %1 from the iPhone?") % bundle_id)
        if reply != QMessageBox.StandardButton.Yes:
            return
        thread = UninstallThread(bundle_id, self._device_udid(), self)
        thread.finished_with_result.connect(self._on_uninstall_done)
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        thread.start()

    def _on_uninstall_done(self, ok, payload):
        self._threads = [t for t in self._threads
                         if not isinstance(t, UninstallThread)]
        if ok:
            self._on_refresh_apps()
        else:
            QMessageBox.warning(self.window, tr("Uninstall Failed"),
                                str(payload))

    # -- manual signing -------------------------------------------------
    def _on_pick_p12(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window, tr("Choose .p12"), "",
            tr("Certificates (*.p12 *.pfx)"))
        if path:
            self._p12_path = path
            self._update_manual_lbl()

    def _on_pick_prov(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window, tr("Choose .mobileprovision"), "",
            tr("Provisioning Profiles (*.mobileprovision)"))
        if path:
            self._prov_path = path
            self._update_manual_lbl()

    def _update_manual_lbl(self):
        parts = []
        if self._p12_path:
            parts.append(os.path.basename(self._p12_path))
        if self._prov_path:
            parts.append(os.path.basename(self._prov_path))
        self._manual_lbl.setText(
            " + ".join(parts) if parts else tr("No certificate selected."))

    def _on_manual_sign(self):
        if not self._ipa_path:
            QMessageBox.warning(self.window, tr("Sign"),
                                tr("Choose an IPA first."))
            return
        if not self._p12_path or not self._prov_path:
            QMessageBox.warning(
                self.window, tr("Sign"),
                tr("Pick both a .p12 certificate and a .mobileprovision "
                   "profile first."))
            return
        password, ok = QInputDialog.getText(
            self.window, tr("Certificate Password"),
            tr("Password for the .p12 (empty if none):"),
            QLineEdit.EchoMode.Password)
        if not ok:
            return
        out, _ = QFileDialog.getSaveFileName(
            self.window, tr("Save Signed IPA"), "",
            tr("iOS Apps (*.ipa)"))
        if not out:
            return
        try:
            from src.sideload.ipaside_engine import signing
            signing.sign_ipa(self._ipa_path, out,
                             p12_path=self._p12_path,
                             p12_password=password,
                             profile_path=self._prov_path)
        except Exception as exc:
            QMessageBox.warning(self.window, tr("Sign Failed"), str(exc))
            return
        QMessageBox.information(
            self.window, tr("Signed"),
            tr("Signed IPA saved. Install it with the Sideload card or "
               "another installer."))

    # -- misc -----------------------------------------------------------
    def refresh(self):
        self.refresh_account()

    def _retheme(self):
        c = self._tm.colors
        self._scroll.setStyleSheet(
            f"background-color: {c.bg_primary}; border: none;")
        self.refresh()
