"""Passcode Themes: import a ``.passthm`` keypad theme and write it to the
device through the cross-platform AirLift driver (``src.airlift``).

The page stages the theme images (``src.tweaks.passcode_theme``) into the
exact file names the passcode keypad expects and pushes them into
``/var/mobile/Library/Caches/TelephonyUI-10`` (or the 9/8 variant for older
iOS). AirLift can only create **new** files — it cannot overwrite an
existing name, so replacing a theme requires removing the old keypad cache
first. The page reports exactly what ``write_files`` reports: a write the
device rejects or drops is a failure (or partial), never a success.
"""

from __future__ import annotations

import asyncio
import logging
import os
import traceback
from typing import Optional

from PySide6.QtCore import Qt, QCoreApplication, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QPushButton, QMessageBox, QFileDialog, QComboBox,
)

from src.airlift import write_files, AirliftError
from src.tweaks.passcode_theme import (
    PASSTHME_TARGET,
    PASSTHME_TARGETS_ALL,
    KEYPAD_LOCALES_ALL,
    PasscodeThemeError,
    parse_passthm,
    stage_files,
    keypad_code_for_locale,
    theme_size,
)
from src.devicemanagement.session import lockdown_session
from pymobiledevice3.exceptions import (
    NotPairedError, PasswordRequiredError, UserDeniedPairingError,
    PairingDialogResponsePendingError, FatalPairingError,
)
from src.gui.ios.components import (
    IOSSectionHeader, IOSCard, IOSPrimaryButton, IOSDangerButton,
)
from src.gui.theme import ColorThemeManager

logger = logging.getLogger("WorkSlop.passthme")

_NUGGET = "Nugget"


def _tr(text: str) -> str:
    return QCoreApplication.translate(_NUGGET, text)


class PasscodeThemeWriteThread(QThread):
    """Background writer: AirLift the staged theme onto the device."""

    progress = Signal(str)
    done = Signal(bool, str)

    def __init__(self, udid: str, theme_path: str, key_digits: int,
                 locale: str, lang_opt: str, bold: str, target_opt: str,
                 parent=None, device_manager=None):
        super().__init__(parent)
        self.udid = udid
        self.theme_path = theme_path
        self.key_digits = key_digits
        self.locale = locale
        self.lang_opt = lang_opt
        self.bold = bold
        self.target_opt = target_opt
        # Fix Audit 5: this write path bypassed the Apply Journal
        # entirely. The thread now opens its own journal before touching
        # the device and (when given the manager) surfaces the path the
        # same way the tweak apply paths do.
        self._device_manager = device_manager
        self.journal_path: Optional[str] = None
        self._journal = None
        self._journal_entry = None

    def _emit(self, message: str):
        # Mirror every ATC/airlift line into the session log too — the status
        # label's last line alone doesn't tell whether the sync observed a
        # tolerated SyncFailed and then completed, or was rejected.
        try:
            logging.getLogger("WorkSlop.passthme").info("atc: %s", message)
        except Exception:
            pass
        self.progress.emit(message)

    # -- Fix Audit 5: Apply Journal for the passcode write ---------------
    def _journal_begin(self):
        """Open the journal and record the request BEFORE any write."""
        try:
            from src.controllers.apply_journal import begin_journal
            journal = begin_journal("apply", device={"udid": self.udid})
            self._journal_entry = journal.add_entry({
                "id": "passcode.theme",
                "tweak_id": "PasscodeTheme",
                "name": "Passcode Theme",
                "family": "Passcode",
                "kind": "special",
                "requested": True,
                "source": "passcode_page",
                "compatibility": {"result": "compatible", "reason": None},
                "hotload": {"result": "allowed", "reason": None},
                "operation": {"theme_file": os.path.basename(self.theme_path)},
            })
            journal.write()
            self._journal = journal
            self.journal_path = journal.path
        except Exception as error:  # journaling must never block a write
            logging.getLogger("WorkSlop.passthme").warning(
                "Passcode Apply Journal begin failed: %s", error)
            self._journal = None
            self._journal_entry = None

    def _journal_stage(self, targets, staged):
        """Attach the staged files and persist the staged state pre-write."""
        journal, entry = self._journal, self._journal_entry
        if journal is None or entry is None:
            return
        try:
            from types import SimpleNamespace
            from src.controllers.apply_journal import TW_STAGED
            entry["operation"].update({
                "targets": list(targets),
                "staged_files": len(staged),
                "locale": self.locale,
                "bold": self.bold,
            })
            records = [
                SimpleNamespace(
                    domain="AirLift",
                    restore_path=f"{target.lstrip('/')}/{name}",
                    contents=data, owner=501, group=501)
                for target in targets for name, data in staged
            ]
            keys = journal.attach_files(records)
            entry["status"] = TW_STAGED
            journal.associate(entry, keys)
            journal.write()
        except Exception as error:
            logging.getLogger("WorkSlop.passthme").warning(
                "Passcode Apply Journal staging failed: %s", error)

    def _journal_finish(self, op_status, entry_status, error=None, note=None):
        journal, entry = self._journal, self._journal_entry
        if journal is None or entry is None:
            return
        try:
            entry["status"] = entry_status
            if note:
                entry["note"] = note
            if error:
                entry["error"] = error
            journal.finalize(op_status, error=error)
            self.journal_path = journal.path
            if self._device_manager is not None:
                self._device_manager.last_apply_journal_path = journal.path
        except Exception as exc:
            logging.getLogger("WorkSlop.passthme").warning(
                "Passcode Apply Journal finalize failed: %s", exc)

    def _targets(self) -> list[str]:
        if self.target_opt == "all":
            return list(PASSTHME_TARGETS_ALL)
        return [f"/var/mobile/Library/Caches/TelephonyUI-{self.target_opt}"]

    def _languages(self):
        if self.lang_opt == "all":
            return "all"
        if self.lang_opt:
            return [self.lang_opt]
        return None

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # Fix Audit 5: journal opens BEFORE the device write (the parse /
        # staging below is local preparation, the write is the apply).
        self._journal_begin()
        try:
            self.progress.emit(_tr("Parsing theme…"))
            keys = parse_passthm(self.theme_path)
            staged = stage_files(
                keys, locale=self.locale, langs=self._languages(), bold=self.bold)
            targets = self._targets()
            self._journal_stage(targets, staged)

            self.progress.emit(
                _tr("Staged {0} key files, {1} targets").format(len(staged), len(targets)))

            written: list[str] = []
            failures: list[str] = []
            rejected = False
            targets_ok = True
            try:
                async def apply_all():
                    nonlocal rejected, targets_ok
                    self.progress.emit(_tr(
                        "Step 1/3 — Trust check: opening a device session. If "
                        "this computer isn't trusted yet, unlock your iPhone "
                        "and tap \u201cTrust This Computer\u201d now."))
                    async with lockdown_session(self.udid) as lockdown:
                        if not getattr(lockdown, "paired", True):
                            # lockdown_session already refuses unpaired clients,
                            # but keep the belt-and-suspenders check so we
                            # never sync against a half-trusted device.
                            raise AirliftError(_tr(
                                "the iPhone did not confirm this computer as "
                                "trusted — tap \u201cTrust This Computer\u201d "
                                "on the device and try again"))
                        self.progress.emit(_tr(
                            "Step 2/3 — Device trust confirmed; staging the "
                            "theme…"))
                        for target in targets:
                            self.progress.emit(
                                _tr("Writing {0} files to {1}…").format(len(staged), target))
                            result = await write_files(
                                lockdown, target, staged, log_cb=self._emit)
                            # Fix Audit 98: honor the per-target verdict.
                            # write_files reports ok/rejected alongside the
                            # written/failures lists; a rejected session or
                            # ok=False must never read as success downstream.
                            target_written = list(result.get("written") or [])
                            target_failures = list(result.get("failures") or [])
                            written.extend(target_written)
                            failures.extend(target_failures)
                            if result.get("rejected"):
                                rejected = True
                            reported_ok = result.get("ok")
                            if reported_ok is None:
                                reported_ok = not target_failures
                            if not reported_ok or target_failures:
                                targets_ok = False
                            if rejected:
                                # The device refused the session itself;
                                # remaining targets would hit the same
                                # refusal — fail fast (AirLift contract).
                                break
                        self.progress.emit(_tr("Step 3/3 — Finishing…"))
                try:
                    loop.run_until_complete(apply_all())
                except PasswordRequiredError:
                    raise RuntimeError(_tr(
                        "The device is locked. Unlock your iPhone, then tap "
                        "\u201cTrust This Computer\u201d when the dialog appears "
                        "and try again."))
                except UserDeniedPairingError:
                    raise RuntimeError(_tr(
                        "You declined the trust request on the device. Connect "
                        "your iPhone, tap \u201cTrust This Computer\u201d and "
                        "try again."))
                except (PairingDialogResponsePendingError, NotPairedError, FatalPairingError):
                    raise RuntimeError(_tr(
                        "The device did not confirm this computer as trusted — "
                        "the Apple\u00ae sync service (ATC) refuses an untrusted "
                        "host and the write would fail. Unlock your iPhone and "
                        "tap \u201cTrust This Computer\u201d, then try again."))
            except (AirliftError, OSError, TimeoutError, ConnectionError) as error:
                raise RuntimeError(f"{type(error).__name__}: {error}") from error

            # Fix Audit 98: report what write_files actually reported.
            # Full success requires every target ok with zero failures;
            # anything else is an honest failure or partial — never a
            # green "success", and never a "skipped, already exists" claim
            # (the AirLift result cannot confirm a file exists on the
            # device; rejection, a dropped session and an existing name
            # all surface as the same failure entry).
            from src.controllers.apply_journal import (
                OP_FAILED, OP_PARTIAL, OP_SUCCESS,
                TW_DELIVERED, TW_NOT_DELIVERED)
            expected = len(staged) * len(targets)
            full_ok = (targets_ok and not rejected and not failures
                       and len(written) >= expected)
            if full_ok:
                self._journal_finish(OP_SUCCESS, TW_DELIVERED)
                self.done.emit(True, _tr(
                    "Wrote {0} file(s) to the device.").format(len(written)))
            elif not written:
                if rejected:
                    message = _tr(
                        "Nothing was written: the device rejected the "
                        "AirLift session. Unlock the iPhone, keep it awake, "
                        "open Apple Books once, and try again.")
                else:
                    message = _tr(
                        "Nothing was written: all {0} file write(s) failed. "
                        "Reconnect the iPhone and try again. If this theme "
                        "is already on the device, remove the old keypad "
                        "cache first — AirLift cannot overwrite existing "
                        "files.").format(expected)
                self._journal_finish(OP_FAILED, TW_NOT_DELIVERED,
                                     error=message)
                self.done.emit(False, message)
            else:
                names = ", ".join(failures[:8])
                if len(failures) > 8:
                    names += ", …"
                failed_note = _tr(" ({0})").format(names) if names else ""
                failed_count = max(len(failures), expected - len(written))
                message = _tr(
                    "Partially written: {0} of {1} file(s) reached the "
                    "device; {2} could not be written{3}. A file that "
                    "already exists on the device cannot be overwritten "
                    "by AirLift, and a dropped or rejected session fails "
                    "the same way — remove the old keypad cache to replace "
                    "an existing theme, or reconnect and retry.").format(
                        len(written), expected, failed_count, failed_note)
                self._journal_finish(
                    OP_PARTIAL, TW_DELIVERED,
                    note=f"{failed_count} of {expected} file write(s) did "
                         "not complete; see the status message.")
                self.done.emit(False, message)
        except Exception as error:
            logging.getLogger("WorkSlop.passthme").error(
                "Passcode theme write failed: %s\n%s", error, traceback.format_exc())
            from src.controllers.apply_journal import (
                OP_FAILED, TW_FAILED, TW_NOT_DELIVERED)
            _entry = self._journal_entry or {}
            self._journal_finish(
                OP_FAILED,
                TW_NOT_DELIVERED if _entry.get("status") == "staged"
                else TW_FAILED,
                error=f"{type(error).__name__}: {error}")
            self.done.emit(False, f"{type(error).__name__}: {error}")
        finally:
            loop.close()


class PasscodeTrustProbeThread(QThread):
    """Live trust probe for the device line (Fix Audit 28).

    Opens a real lockdown session with ``autopair=False`` (the same
    ``lockdown_session`` + ``paired`` check the write path uses) so the
    label reflects the device's CURRENT trust state instead of the
    enumeration-time cache, which can be stale in both directions: a
    device trusted since enumeration was still labelled untrusted, and
    a device whose trust was revoked was still labelled trusted.
    ``autopair=False`` keeps merely *showing* the page from popping a
    "Trust This Computer" dialog on the phone.
    """

    probed = Signal(bool, bool, str)  # reachable, trusted, detail

    def __init__(self, udid: str, parent=None):
        super().__init__(parent)
        self.udid = udid

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def probe():
                async with lockdown_session(
                        self.udid, autopair=False,
                        pair_timeout=10.0) as lockdown:
                    return bool(getattr(lockdown, "paired", False))

            trusted = loop.run_until_complete(probe())
            self.probed.emit(True, trusted, "")
        except Exception as error:  # device unreachable / session refused
            self.probed.emit(False, False, f"{type(error).__name__}: {error}")
        finally:
            loop.close()


class IOSPasscodeThemePage(QWidget):
    """iOS-style page to import a ``.passthm`` and push it to the device."""

    LANG_DEVICE = ""
    LANG_ALL = "all"

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("iosContainer")

        self._theme_path: Optional[str] = None
        self._key_digits = 0
        self._worker: Optional[PasscodeThemeWriteThread] = None
        self._trust_probe: Optional[PasscodeTrustProbeThread] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        content = QWidget()
        self._scroll.setWidget(content)
        layout.addWidget(self._scroll)

        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(16, 16, 16, 32)
        self.content_layout.setSpacing(8)

        self._hint = QLabel(_tr(
            "Customize the Passcode keypad with a theme package (.passthm) — "
            "images, sub-labels and bold keys. Themes are written straight to "
            "the device over USB/Wi-Fi (no reboot).\n\n"
            "AirLift only creates NEW files on the device: re-applying the "
            "same theme is a no-op, and replacing an existing theme with "
            "different art requires removing the old keypad cache first."))
        self._hint.setWordWrap(True)
        self.content_layout.addWidget(self._hint)

        # ---- Theme --------------------------------------------------------
        self.content_layout.addWidget(IOSSectionHeader(_tr("Theme")))

        self.theme_placeholder = QLabel(_tr("No theme selected yet."))
        self.theme_placeholder.setAlignment(Qt.AlignCenter)
        self.theme_placeholder.setStyleSheet("padding: 24px 0;")
        self.content_layout.addWidget(self.theme_placeholder)

        self._theme_card_box = QVBoxLayout()
        self._theme_card_box.setSpacing(8)
        self.content_layout.addLayout(self._theme_card_box)

        self._choose_btn = IOSPrimaryButton(_tr("Choose .passthm…"))
        self._choose_btn.clicked.connect(self.choose_theme_dialog)
        self.content_layout.addWidget(self._choose_btn)

        # ---- Options ------------------------------------------------------
        self.content_layout.addWidget(IOSSectionHeader(_tr("Options")))

        options_card = IOSCard()
        options_layout = QVBoxLayout(options_card)
        options_layout.setContentsMargins(16, 12, 16, 12)
        options_layout.setSpacing(12)

        self._lang_combo = QComboBox()
        options_layout.addLayout(self._row(
            _tr("Keypad Language"), self._lang_combo))
        self._populate_lang_combo()

        self._bold_combo = QComboBox()
        options_layout.addLayout(self._row(_tr("Bold Keys"), self._bold_combo))
        self._populate_bold_combo()

        self._target_combo = QComboBox()
        options_layout.addLayout(self._row(
            _tr("Target TelephonyUI"), self._target_combo))
        self._populate_target_combo()

        self.content_layout.addWidget(options_card)

        # ---- Write to device ----------------------------------------------
        self.content_layout.addWidget(IOSSectionHeader(_tr("Write to device")))

        self._device_lbl = QLabel("")
        self._device_lbl.setWordWrap(True)
        self.content_layout.addWidget(self._device_lbl)

        self._write_btn = IOSPrimaryButton(_tr("Write Theme to Device"))
        self._write_btn.clicked.connect(self.start_write)
        self.content_layout.addWidget(self._write_btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.hide()
        self.content_layout.addWidget(self._status_lbl)

        self.content_layout.addStretch()

        self._retheme()
        self._load_settings()
        self._refresh_device_line()

    def _row(self, label: str, widget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        text = QLabel(label)
        text.setWordWrap(True)
        row.addWidget(text, 1)
        row.addWidget(widget)
        return row

    def _populate_lang_combo(self):
        self._lang_combo.blockSignals(True)
        self._lang_combo.clear()
        self._lang_combo.addItem(_tr("Device Language"), self.LANG_DEVICE)
        self._lang_combo.addItem(_tr("All Languages"), self.LANG_ALL)
        for code in KEYPAD_LOCALES_ALL:
            self._lang_combo.addItem(self._lang_label(code), code)
        self._lang_combo.blockSignals(False)

    @staticmethod
    def _lang_label(code: str) -> str:
        names = {
            "en": "English", "other": "Others", "ru": "Русский", "uk": "Українська",
            "es": "Español", "fr": "Français", "de": "Deutsch", "it": "Italiano",
            "pt": "Português", "tr": "Türkçe", "pl": "Polski", "nl": "Nederlands",
            "ja": "日本語", "ko": "한국어", "zh": "中文", "ar": "العربية", "he": "עברית",
        }
        return f"{code} — {names.get(code, code)}"

    def _populate_bold_combo(self):
        self._bold_combo.blockSignals(True)
        self._bold_combo.clear()
        self._bold_combo.addItem(_tr("Both (Regular + Bold)"), "both")
        self._bold_combo.addItem(_tr("Regular only"), "regular")
        self._bold_combo.addItem(_tr("Bold only"), "bold")
        self._bold_combo.blockSignals(False)

    def _populate_target_combo(self):
        self._target_combo.blockSignals(True)
        self._target_combo.clear()
        self._target_combo.addItem("TelephonyUI-10 (iOS 27)", "10")
        self._target_combo.addItem("TelephonyUI-9 (iOS 26.x)", "9")
        self._target_combo.addItem("TelephonyUI-8 (older)", "8")
        self._target_combo.addItem(_tr("All (8, 9, 10)"), "all")
        self._target_combo.blockSignals(False)

    # ---- theme lifecycle -------------------------------------------------

    def _load_settings(self):
        settings = self.window.settings
        path = settings.value("passcode_theme_path", "", type=str)
        if path and os.path.isfile(path):
            try:
                keys = parse_passthm(path)
                self._apply_theme(path, keys)
            except (PasscodeThemeError, OSError):
                settings.setValue("passcode_theme_path", "")
        lang = settings.value("passcode_theme_lang", self.LANG_DEVICE, type=str)
        bold = settings.value("passcode_theme_bold", "both", type=str)
        target = settings.value("passcode_theme_target", "10", type=str)
        self._set_combo_value(self._lang_combo, lang, self.LANG_DEVICE)
        self._set_combo_value(self._bold_combo, bold, "both")
        self._set_combo_value(self._target_combo, target, "10")
        self._refresh_theme_area()

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str, default: str):
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else combo.findData(default))

    def _save_options(self):
        settings = self.window.settings
        settings.setValue("passcode_theme_lang",
                          self._lang_combo.currentData())
        settings.setValue("passcode_theme_bold",
                          self._bold_combo.currentData())
        settings.setValue("passcode_theme_target",
                          self._target_combo.currentData())
        self.window._sync_settings()

    def choose_theme_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, _tr("Choose a Passcode Theme"), "", _tr("passthemes (*.passthm)"))
        if not path:
            return
        try:
            keys = parse_passthm(path)
        except PasscodeThemeError as error:
            QMessageBox.warning(self.window, _tr("Invalid Theme"),
                                f"{type(error).__name__}: {error}")
            return
        self._apply_theme(path, keys)
        self.window.settings.setValue("passcode_theme_path", path)
        self.window._sync_settings()

    def _apply_theme(self, path: str, keys: dict[str, bytes]):
        self._theme_path = path
        self._key_digits = len(keys)
        self._refresh_theme_area()

    def _remove_theme(self):
        self._theme_path = None
        self._key_digits = 0
        self.window.settings.setValue("passcode_theme_path", "")
        self.window._sync_settings()
        self._refresh_theme_area()

    def _refresh_theme_area(self):
        c = ColorThemeManager.instance().colors
        has_theme = self._theme_path is not None
        self.theme_placeholder.setVisible(not has_theme)
        while self._theme_card_box.count():
            item = self._theme_card_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not has_theme:
            return
        card = IOSCard()
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 12, 12, 12)
        row.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name = QLabel(os.path.basename(self._theme_path) or self._theme_path)
        name.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {c.text_primary};")
        name.setWordWrap(True)
        text_col.addWidget(name)
        size = theme_size(self._theme_path)
        size_hint = ""
        if size == 1:
            size_hint = _tr(", small keys")
        elif size == 2:
            size_hint = _tr(", big keys")
        detail = QLabel(_tr("{0} key images{1}").format(self._key_digits, size_hint))
        detail.setStyleSheet(f"font-size: 12px; color: {c.text_secondary};")
        text_col.addWidget(detail)
        row.addLayout(text_col, 1)

        remove_btn = QPushButton(_tr("Remove"))
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c.surface_hover}; color: {c.error}; "
            f"border: 1px solid {c.border}; border-radius: 12px; padding: 8px 14px; }}"
            f"QPushButton:hover {{ background-color: {c.error}; color: {c.text_inverse}; }}")
        remove_btn.clicked.connect(self._remove_theme)
        row.addWidget(remove_btn)
        self._theme_card_box.addWidget(card)

    # ---- write flow ------------------------------------------------------

    def _device_locale(self) -> str:
        try:
            device = self.window.device_manager.data_singleton.current_device
            return getattr(device, "locale", "") or ""
        except Exception:
            return ""

    def refresh(self):
        # REAUDIT FIX: called on page navigation (see _update_shared_nav) so
        # the device line reflects the currently connected iPhone instead of
        # the construction-time "No trusted iPhone connected" text.
        self._refresh_device_line()

    def _cached_device(self):
        try:
            return self.window.device_manager.data_singleton.current_device
        except Exception:
            return None

    def _device_identity_text(self, device) -> str:
        version = getattr(device, "version", "")
        build = getattr(device, "build", "")
        model = getattr(device, "model", "")
        return _tr("Device: {0} — iOS {1} ({2}).").format(
            model or _tr("iPhone"), version or "?", build or "?")

    def _refresh_device_line(self):
        # Fix Audit 28: the trust label used to be read straight from
        # the enumeration-time ``current_device`` cache, which goes
        # stale in both directions. The cache now only identifies the
        # device and serves as a clearly-labelled fallback; the trust
        # claim itself comes from a live probe (see _start_trust_probe)
        # every time the page is shown.
        c = ColorThemeManager.instance().colors
        device = self._cached_device()
        if device is None:
            self._device_lbl.setText(_tr(
                "No trusted iPhone connected. Plug it in, unlock it, tap "
                "\u201cTrust This Computer\u201d when iOS asks, and wait for it "
                "to appear here."))
            self._device_lbl.setStyleSheet(f"color: {c.error}; font-size: 13px;")
            return
        self._device_lbl.setText(
            self._device_identity_text(device) + " " + _tr(
                "Checking whether this computer is trusted — live, on "
                "the device…"))
        self._device_lbl.setStyleSheet(f"color: {c.text_secondary}; font-size: 13px;")
        self._start_trust_probe()

    def _start_trust_probe(self):
        if self._trust_probe is not None and self._trust_probe.isRunning():
            return
        try:
            udid = self.window.device_manager.get_current_device_udid()
        except Exception:
            udid = None
        if not udid:
            self._show_cached_trust_fallback()
            return
        self._trust_probe = PasscodeTrustProbeThread(udid, parent=self)
        self._trust_probe.probed.connect(self._on_trust_probed)
        self._trust_probe.finished.connect(self._trust_probe.deleteLater)
        self._trust_probe.start()

    def _show_cached_trust_fallback(self):
        """Cache-based label, explicitly marked as a fallback.

        Used only when no live probe can run (no UDID, or the device
        could not be reached): the text never claims trust as a live
        fact, it says the status is the cached one.
        """
        c = ColorThemeManager.instance().colors
        device = self._cached_device()
        if device is None:
            return
        self._device_lbl.setText(
            self._device_identity_text(device) + " " + _tr(
                "Trust status shown from the last device scan (cached) — "
                "the device could not be reached for a live trust check, "
                "so this may be out of date."))
        self._device_lbl.setStyleSheet(f"color: {c.error}; font-size: 13px;")

    def _on_trust_probed(self, reachable: bool, trusted: bool, detail: str):
        self._trust_probe = None
        c = ColorThemeManager.instance().colors
        device = self._cached_device()
        if device is None:
            self._refresh_device_line()
            return
        if not reachable:
            self._show_cached_trust_fallback()
            return
        identity = self._device_identity_text(device)
        if trusted:
            self._device_lbl.setText(identity + " " + _tr(
                "This computer is trusted by it (checked live just now), "
                "so the write runs immediately — no \u201cTrust This "
                "Computer\u201d pop-up will appear."))
            self._device_lbl.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 13px;")
        else:
            self._device_lbl.setText(identity + " " + _tr(
                "This computer is NOT trusted by it (checked live just "
                "now). Unlock the iPhone and tap \u201cTrust This "
                "Computer\u201d, then reopen this page."))
            self._device_lbl.setStyleSheet(f"color: {c.error}; font-size: 13px;")
            return
        try:
            available = self.window.device_manager.data_singleton.device_available
        except Exception:
            available = True
        if not available:
            self._device_lbl.setText(identity + " " + _tr(
                "Device present, but it is not supported for AirLift (needs an "
                "iPhone on iOS 26.2+)."))
            self._device_lbl.setStyleSheet(f"color: {c.error}; font-size: 13px;")

    def start_write(self):
        self._save_options()
        self._refresh_device_line()
        if not self._theme_path:
            self._show_status(_tr("Choose a theme first."), "error")
            return
        udid = self.window.device_manager.get_current_device_udid()
        if not udid:
            self._show_status(
                _tr("No trusted iPhone is listed. Plug it in, unlock it, tap "
                    "\u201cTrust This Computer\u201d when iOS asks, then wait "
                    "for it to appear."),
                "error")
            return
        if not self.window.device_manager.data_singleton.device_available:
            self._show_status(
                _tr("This device is not supported for AirLift (needs an "
                    "iPhone on iOS 26.2+)."),
                "error")
            return

        if self._worker is not None and self._worker.isRunning():
            self._show_status(_tr("A write is already running."), "info")
            return

        locale = self._device_locale()
        self._write_btn.setEnabled(False)
        self._show_status(_tr("Starting…"), "info")

        self._worker = PasscodeThemeWriteThread(
            udid=udid,
            theme_path=self._theme_path,
            key_digits=self._key_digits,
            locale=locale,
            lang_opt=self._lang_combo.currentData(),
            bold=self._bold_combo.currentData(),
            target_opt=self._target_combo.currentData(),
            device_manager=self.window.device_manager,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        # Clean teardown: deleteLater after run() returns, and only drop our
        # reference once the native thread is finished (clearing it in
        # ``_on_done`` would free the QThread object while run() is still
        # winding down -> "QThread: Destroyed while thread '...' is still
        # running" hard abort at app shutdown).
        self._worker.finished.connect(self._on_write_thread_finished)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_progress(self, message: str):
        self._show_status(message, "info")

    def _on_done(self, success: bool, message: str):
        self._write_btn.setEnabled(True)
        self._show_status(message, "success" if success else "error")
        try:
            if self.window.isVisible():
                QMessageBox.information(
                    self.window,
                    _tr("Passcode Theme"),
                    message if success else _tr("Apply failed:\n\n{0}").format(message),
                )
        except RuntimeError:
            pass

    def _on_write_thread_finished(self):
        # run() returned, so the native thread is done; drop the reference
        # (deleteLater is already queued via the other connection).
        try:
            self._worker = None
        except Exception:
            pass

    def _show_status(self, text: str, kind: str):
        c = ColorThemeManager.instance().colors
        color = {"success": c.success, "error": c.error}.get(kind, c.accent)
        self._status_lbl.setStyleSheet(f"font-size: 13px; color: {color};")
        self._status_lbl.setText(text)
        self._status_lbl.show()

    # ---- theme reactivity --------------------------------------------------

    def _retheme(self):
        c = ColorThemeManager.instance().colors
        self._scroll.setStyleSheet(
            f"background-color: {c.bg_primary}; border: none;")
        self._hint.setStyleSheet(f"color: {c.text_secondary}; font-size: 13px;")
        self.theme_placeholder.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 15px; padding: 24px 0;")
        self._lang_combo.setStyleSheet(
            f"QComboBox {{ background-color: {c.bg_secondary}; color: {c.text_primary}; "
            f"border: 1px solid {c.border}; border-radius: 10px; padding: 6px 10px; }}")
        self._bold_combo.setStyleSheet(self._lang_combo.styleSheet())
        self._target_combo.setStyleSheet(self._lang_combo.styleSheet())
        self._status_lbl.setStyleSheet(f"font-size: 13px; color: {c.accent};")
        self._refresh_theme_area()
        self._refresh_device_line()