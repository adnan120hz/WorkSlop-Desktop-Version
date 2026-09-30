"""QThread workers for the Sideloading page.

All Apple-facing work (GSA login, signing, installation) is blocking I/O,
so it runs here off the UI thread. Results come back through Qt signals.

The workers drive the vendored engine in ``src.sideload.ipaside_engine``
(MIT, see ``src/sideload/ATTRIBUTION.md``) — the same GrandSlam/SRP + anisette
login and developerservices2 provisioning flow Sideloadly-style tools use.
The Apple ID password is kept only in memory for the duration of the login
call and is never written to disk or settings.

Every worker also mirrors its progress into the session log file
(``logging.getLogger("WorkSlop.sideload")``). The file handler flushes after
each record, so even if the process is force-closed mid-login the log on disk
still shows the last completed step — the GUI label alone dies with the
process. Never log the password, 2FA code, or any token here.
"""
import logging

from PySide6.QtCore import QThread, Signal

_slog = logging.getLogger("WorkSlop.sideload")


def _logged_progress(emit, tag: str):
    """Wrap a progress callback so each stage is also written to the session log."""
    def _cb(*args):
        try:
            text = " ".join(str(a) for a in args if a is not None)
        except Exception:
            text = "<progress>"
        if text:
            _slog.info("[%s] %s", tag, text)
        try:
            emit(*args)
        except Exception:
            pass
    return _cb


class LoginThread(QThread):
    """Apple ID sign-in. Handles the 2FA round-trip via signals."""

    # Emitted when Apple asks for a 2FA code: (method,) — "trusted" or "sms".
    # The page must then call submit_2fa(code) on this thread.
    twofa_required = Signal(str)
    # Live stage text so the UI never sits silent during the network calls.
    progress = Signal(str)
    # (ok, message)
    finished_with_result = Signal(bool, str)

    def __init__(self, email: str, password: str, parent=None):
        super().__init__(parent)
        self._email = email
        self._password = password
        self._code = None
        self._code_ready = False
        # simple in-thread event loop for the 2FA handoff
        import threading
        self._event = threading.Event()

    def submit_2fa(self, code: str):
        self._code = code
        self._code_ready = True
        self._event.set()

    def run(self):
        from src.sideload.ipaside_engine import gsa
        _slog.info("[login] thread started for %s", self._email)
        progress = _logged_progress(self.progress.emit, "login")
        try:
            result = gsa.begin_login(
                self._email, self._password,
                on_progress=progress)
            if isinstance(result, dict) and result.get("status") == "2fa_required":
                method = result.get("method", "trusteddevice")
                _slog.info("[login] 2FA required (method=%s), waiting for code", method)
                self.twofa_required.emit(method)
                # Wait for the page to hand us the code (5-minute cap).
                if not self._event.wait(timeout=300):
                    _slog.warning("[login] timed out waiting for 2FA code")
                    self.finished_with_result.emit(
                        False, "Timed out waiting for the verification code.")
                    return
                if not self._code_ready or not self._code:
                    _slog.warning("[login] 2FA cancelled by user")
                    self.finished_with_result.emit(
                        False, "Verification cancelled.")
                    return
                _slog.info("[login] 2FA code received, completing login")
                result = gsa.complete_2fa(
                    self._email, self._password, self._code.strip(),
                    on_progress=progress)
            if isinstance(result, dict) and result.get("status") == "authenticated":
                _slog.info("[login] authenticated as %s", self._email)
                self.finished_with_result.emit(
                    True, f"Signed in as {self._email}.")
            else:
                detail = result.get("error") if isinstance(result, dict) else None
                _slog.warning("[login] failed: %s", detail or result)
                self.finished_with_result.emit(
                    False, str(detail or result or "Unknown login error."))
        except Exception as exc:  # GsaError and friends carry human text
            _slog.exception("[login] exception")
            self.finished_with_result.emit(False, str(exc))
        finally:
            # Never retain the password longer than the login attempt.
            self._password = ""
            self._code = ""


class SideloadThread(QThread):
    """Sign an IPA with the Apple ID's dev certificate and install it."""

    progress = Signal(int, str)          # percent, stage text
    finished_with_result = Signal(bool, str)

    def __init__(self, ipa_path: str, udid: str | None,
                 bundle_id: str | None = None,
                 display_name: str | None = None,
                 parent=None):
        super().__init__(parent)
        self._ipa_path = ipa_path
        self._udid = udid
        self._bundle_id = bundle_id
        self._display_name = display_name

    def _on_progress(self, stage: str, value, message: str | None):
        try:
            pct = int(value) if isinstance(value, (int, float)) else -1
        except Exception:
            pct = -1
        text = message or stage
        self.progress.emit(pct, f"{stage}: {text}" if stage else text)

    def run(self):
        from src.sideload.ipaside_engine import sideload
        _slog.info("[sideload] thread started: ipa=%s udid=%s bundle=%s",
                   self._ipa_path, self._udid, self._bundle_id)
        try:
            result = sideload.run_sideload(
                self._ipa_path,
                self._udid,
                bundle_id=self._bundle_id,
                display_name=self._display_name,
                on_progress=_logged_progress(self._on_progress, "sideload"),
            )
            app = result.get("name") or result.get("bundle_id") or "App"
            _slog.info("[sideload] installed: %s", app)
            self.finished_with_result.emit(
                True, f"{app} installed on the iPhone.")
        except Exception as exc:
            _slog.exception("[sideload] exception")
            self.finished_with_result.emit(False, str(exc))


class InstalledAppsThread(QThread):
    """List user-installed apps on the connected iPhone."""

    finished_with_result = Signal(bool, object)  # ok, list[dict] | error str

    def __init__(self, udid: str | None, parent=None):
        super().__init__(parent)
        self._udid = udid

    def run(self):
        from src.sideload.ipaside_engine import apps as engine_apps
        try:
            raw = engine_apps.list_installed(serial=self._udid, app_type="User")
            result = []
            for bundle_id, info in (raw or {}).items():
                if not isinstance(info, dict):
                    continue
                result.append({
                    "bundle_id": bundle_id,
                    "name": info.get("CFBundleDisplayName")
                    or info.get("CFBundleName") or bundle_id,
                    "version": info.get("CFBundleShortVersionString", ""),
                })
            result.sort(key=lambda a: a["name"].lower())
            self.finished_with_result.emit(True, result)
        except Exception as exc:
            self.finished_with_result.emit(False, str(exc))


class UninstallThread(QThread):
    finished_with_result = Signal(bool, str)

    def __init__(self, bundle_id: str, udid: str | None, parent=None):
        super().__init__(parent)
        self._bundle_id = bundle_id
        self._udid = udid

    def run(self):
        from src.sideload.ipaside_engine import apps as engine_apps
        try:
            engine_apps.uninstall(self._bundle_id, serial=self._udid)
            self.finished_with_result.emit(True, self._bundle_id)
        except Exception as exc:
            self.finished_with_result.emit(False, str(exc))


class ServiceStartThread(QThread):
    """Start Apple's Mobile Device Service on Windows (UAC prompt handled
    by the engine). Off the UI thread because elevation can take a while."""

    finished_with_result = Signal(bool, str)  # ok, human-readable message

    def run(self):
        from src.sideload.ipaside_engine import apple_support
        try:
            result = apple_support.start_service()
            ok = bool(result.get("started"))
            self.finished_with_result.emit(ok, str(result.get("detail", "")))
        except Exception as exc:
            self.finished_with_result.emit(False, str(exc))


class SignOnlyThread(QThread):
    """Manual IPA signing with a user-supplied .p12 + .mobileprovision.

    Runs off the UI thread so the page stays responsive while zsign works.
    """

    finished_with_result = Signal(bool, str)  # ok, output path | error text

    def __init__(self, input_ipa: str, output_ipa: str, p12_path: str,
                 p12_password: str, profile_path: str, parent=None):
        super().__init__(parent)
        self._input_ipa = input_ipa
        self._output_ipa = output_ipa
        self._p12_path = p12_path
        self._p12_password = p12_password
        self._profile_path = profile_path

    def run(self):
        from src.sideload.ipaside_engine import signing
        try:
            signing.sign_ipa(
                self._input_ipa, self._output_ipa,
                p12_path=self._p12_path,
                p12_password=self._p12_password,
                profile_path=self._profile_path)
            self.finished_with_result.emit(True, self._output_ipa)
        except Exception as exc:
            self.finished_with_result.emit(False, str(exc))
        finally:
            # Don't keep the certificate password in memory longer than needed.
            self._p12_password = ""
