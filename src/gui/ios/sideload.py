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
    QMessageBox, QLineEdit, QProgressBar, QProgressDialog, QInputDialog,
    QListWidget, QListWidgetItem, QCheckBox, QTextEdit, QApplication,
)

from src.gui.ios.components import IOSCard, IOSPrimaryButton, IOSSectionHeader
from src.gui.theme import t, ColorThemeManager
from src.gui.thread_workers.sideload_worker import (
    LoginThread, SideloadThread, InstalledAppsThread, UninstallThread,
    SignOnlyThread, ServiceStartThread,
)


def tr(text: str, disambiguation: str = "", n: int = -1) -> str:
    return QCoreApplication.translate("Nugget", text, disambiguation, n)


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
        self._sign_thread = None
        self._sign_btn = None
        self._sign_progress = None

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
        self._content_layout.addWidget(self._make_log_card())

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
        self._sign_btn = sign_btn
        lay.addLayout(row)
        return card

    def _make_log_card(self):
        # Copyable log: every sideload event lands here with a timestamp,
        # selectable and copyable (the old status label could not be copied).
        card, lay = self._make_card_shell(tr("Log"))
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMinimumHeight(150)
        self._log_view.setMaximumHeight(260)
        self._log_view.setLineWrapMode(QTextEdit.NoWrap)
        lay.addWidget(self._log_view)
        row = QHBoxLayout()
        row.addStretch(1)
        copy_btn = IOSPrimaryButton(tr("Copy Log"))
        copy_btn.clicked.connect(self._on_copy_log)
        row.addWidget(copy_btn)
        save_btn = IOSPrimaryButton(tr("Save Log..."))
        save_btn.clicked.connect(self._on_save_log)
        row.addWidget(save_btn)
        clear_btn = IOSPrimaryButton(tr("Clear"))
        clear_btn.clicked.connect(self._log_view.clear)
        row.addWidget(clear_btn)
        lay.addLayout(row)
        self._style_log_view()
        return card

    def _style_log_view(self):
        c = self._tm.colors
        self._log_view.setStyleSheet(
            f"QTextEdit {{ background-color: {c.bg_input}; "
            f"color: {c.text_primary}; border: 1px solid {c.divider}; "
            f"border-radius: 8px; padding: 8px; "
            f"font-family: monospace; font-size: 12px; }}")

    def _log_line(self, text):
        # Called from GUI-thread slots only (all worker output arrives via
        # signals), so direct append is thread-safe.
        from datetime import datetime
        stamp = datetime.now().strftime("%H:%M:%S")
        self._log_view.append(f"[{stamp}] {text}")

    def _on_copy_log(self):
        QApplication.clipboard().setText(self._log_view.toPlainText())
        self._log_line(tr("Log copied to clipboard."))

    def _on_save_log(self):
        from datetime import datetime
        default = f"workslop-sideload-{datetime.now():%Y%m%d-%H%M%S}.log"
        path, _ = QFileDialog.getSaveFileName(
            self.window, tr("Save Sideload Log"), default,
            tr("Log Files (*.log);;Text Files (*.txt)"))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._log_view.toPlainText())
            self._log_line(tr("Log saved to %1") % path)
        except OSError as exc:
            QMessageBox.warning(self.window, tr("Save Log"),
                                tr("Could not save log: %1") % str(exc))

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
        self._log_line(tr("Signing in as %1...") % email)
        thread = LoginThread(email, password, self)
        thread.twofa_required.connect(self._on_2fa_required)
        thread.progress.connect(self._on_login_progress)
        thread.finished_with_result.connect(self._on_login_done)
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        self._login_thread = thread
        thread.start()

    def _on_login_progress(self, stage):
        # Live log line while the login network calls run, so the page never
        # sits silent on "Signing in...". Also mirrored into the copyable log.
        if getattr(self, "_login_thread", None) is not None:
            self._account_status.setText(str(stage))
            if str(stage) != getattr(self, "_last_login_stage", None):
                self._last_login_stage = str(stage)
                self._log_line(str(stage))

    def _on_2fa_required(self, method):
        self._log_line(tr("Apple requires two-factor authentication (%1).")
                       % ("SMS" if method == "sms" else tr("trusted device")))
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
        self._last_login_stage = None
        self._log_line((tr("Signed in: %1") if ok
                        else tr("Sign in failed: %1")) % message)
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
        # HONESTY-AUDIT FIX: this used to read `self.window.dev`, an
        # attribute that does not exist on the main window — so every
        # sideload / installed-apps / uninstall call silently got None and
        # reported "No iPhone connected". The canonical accessor used by
        # every other page is device_manager.get_current_device_udid().
        try:
            return self.window.device_manager.get_current_device_udid()
        except Exception:
            return None

    def _device_or_diagnose(self, action):
        """Return the UDID, or — on Windows with no device — diagnose the
        real cause instead of blaming the cable.

        "No iPhone connected" is the wrong message when Apple's driver
        stack (Apple Mobile Device Service) is stopped or missing; the
        engine knows the difference, so ask it before giving up.
        """
        udid = self._device_udid()
        if udid:
            return udid
        import os
        if os.name == "nt":
            try:
                from src.sideload.ipaside_engine import apple_support
                report = apple_support.status()
                state = report.get("state")
                detail = report.get("detail", "")
                self._log_line(tr("Windows device-stack check: %1") % detail)
                if state == apple_support.STOPPED:
                    self._offer_service_start(detail)
                    return None
                if state == apple_support.MISSING:
                    QMessageBox.warning(
                        self.window, tr("Apple Driver Missing"),
                        tr("No iPhone can be seen because Apple's device "
                           "driver is not installed on this PC.\n\n%1\n\n"
                           "Install iTunes from apple.com or the "
                           "\"Apple Devices\" app from the Microsoft Store, "
                           "then reconnect the iPhone.") % detail)
                    return None
            except Exception as exc:
                self._log_line(tr("Device-stack check failed: %1") % str(exc))
        QMessageBox.warning(
            self.window, action,
            tr("No iPhone connected. Connect it over USB, unlock it and "
               "tap Trust, then try again."))
        return None

    def _offer_service_start(self, detail):
        reply = QMessageBox.question(
            self.window, tr("Apple Service Stopped"),
            detail + tr("\n\nStart the Apple Mobile Device Service now? "
                        "Windows will ask for administrator permission."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._log_line(tr("Starting Apple Mobile Device Service..."))
        thread = ServiceStartThread(self)
        thread.finished_with_result.connect(self._on_service_started)
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        thread.start()

    def _on_service_started(self, ok, message):
        self._threads = [t for t in self._threads
                         if not isinstance(t, ServiceStartThread)]
        self._log_line((tr("Service started: %1") if ok
                        else tr("Service start failed: %1")) % message)
        if ok:
            QMessageBox.information(
                self.window, tr("Apple Service"),
                message + tr("\n\nReconnect the iPhone if it is not "
                             "detected yet."))
        else:
            QMessageBox.warning(self.window, tr("Apple Service"), message)

    def _on_sideload(self):
        if not self._ipa_path:
            QMessageBox.warning(self.window, tr("Sideload"),
                                tr("Choose an IPA first."))
            return
        udid = self._device_or_diagnose(tr("Sideload"))
        if not udid:
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
        self._log_line(tr("Sideloading %1...") % os.path.basename(self._ipa_path))
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
        # Log stage transitions only — install progress ticks every percent.
        if text != getattr(self, "_last_sideload_stage", None):
            self._last_sideload_stage = text
            self._log_line(text)

    def _on_sideload_done(self, ok, message):
        self._threads = [t for t in self._threads
                         if not isinstance(t, SideloadThread)]
        self._sideload_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._progress_lbl.setVisible(False)
        self._last_sideload_stage = None
        self._log_line((tr("Sideload finished: %1") if ok
                        else tr("Sideload failed: %1")) % message)
        if ok:
            QMessageBox.information(self.window, tr("Sideload"), message)
            self._on_refresh_apps()
        else:
            QMessageBox.warning(self.window, tr("Sideload Failed"), message)

    # -- installed apps -------------------------------------------------
    def _on_refresh_apps(self):
        udid = self._device_or_diagnose(tr("Installed Apps"))
        if not udid:
            return
        self._log_line(tr("Listing installed apps..."))
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
            self._log_line(tr("Failed to list apps: %1") % str(payload))
            item = QListWidgetItem(tr("Failed: ") + str(payload))
            item.setFlags(Qt.NoItemFlags)
            self._apps_list.addItem(item)
            return
        self._log_line(tr("Found %n installed app(s).", "", len(payload)))
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
        udid = self._device_or_diagnose(tr("Uninstall"))
        if not udid:
            return
        self._log_line(tr("Uninstalling %1...") % str(bundle_id))
        thread = UninstallThread(bundle_id, udid, self)
        thread.finished_with_result.connect(self._on_uninstall_done)
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        thread.start()

    def _on_uninstall_done(self, ok, payload):
        self._threads = [t for t in self._threads
                         if not isinstance(t, UninstallThread)]
        self._log_line((tr("Uninstalled: %1") if ok
                        else tr("Uninstall failed: %1")) % str(payload))
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
        if self._sign_thread is not None:
            return  # a signing run is already in progress
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
        # Sign off the UI thread so the page stays responsive while zsign
        # works (signing an IPA can take a while on large apps).
        self._log_line(tr("Signing %1 with manual certificate...")
                       % os.path.basename(self._ipa_path))
        thread = SignOnlyThread(
            self._ipa_path, out, self._p12_path, password,
            self._prov_path, self)
        password = ""
        thread.finished_with_result.connect(self._on_sign_finished)
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        self._sign_thread = thread
        if self._sign_btn is not None:
            self._sign_btn.setEnabled(False)
        progress = QProgressDialog(
            tr("Signing IPA..."), None, 0, 0, self.window)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        self._sign_progress = progress
        progress.show()
        thread.start()

    def _on_sign_finished(self, ok, message):
        self._threads = [t for t in self._threads
                         if t is not getattr(self, "_sign_thread", None)]
        self._sign_thread = None
        if self._sign_progress is not None:
            self._sign_progress.close()
            self._sign_progress = None
        if self._sign_btn is not None:
            self._sign_btn.setEnabled(True)
        self._log_line((tr("Signed IPA saved: %1") if ok
                        else tr("Sign failed: %1")) % message)
        if ok:
            QMessageBox.information(
                self.window, tr("Signed"),
                tr("Signed IPA saved. Install it with the Sideload card or "
                   "another installer."))
        else:
            QMessageBox.warning(self.window, tr("Sign Failed"), message)

    # -- misc -----------------------------------------------------------
    def refresh(self):
        self.refresh_account()

    def _retheme(self):
        c = self._tm.colors
        self._scroll.setStyleSheet(
            f"background-color: {c.bg_primary}; border: none;")
        if hasattr(self, "_log_view"):
            self._style_log_view()
        self.refresh()
