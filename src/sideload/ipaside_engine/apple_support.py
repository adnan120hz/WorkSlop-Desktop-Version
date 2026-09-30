"""Apple's device stack on Windows: whether it is there, and how to get it.

Everything iPASide does to a phone goes through usbmuxd, and on Windows usbmuxd
ships inside Apple's **Apple Mobile Device Service** (AMDS) - installed by iTunes
or by Apple's "Apple Devices" app. Without that service there is no device I/O at
all: not over USB, and not over Wi-Fi either, since usbmux brokers both. So
"no device connected - plug in your iPhone and tap Trust" is the wrong thing to
tell someone whose actual problem is that Apple's driver stack was never
installed, and this module exists so the app can tell them the truth instead.

It is the single source of truth for that question: :func:`status` answers it and
``doctor._check_amds`` reports *this* answer rather than probing separately, so the
Home screen, the Sideload screen and Diagnostics cannot disagree with each other.

Three answers matter, because the fix differs for each:

* :data:`RUNNING` - nothing to do;
* :data:`STOPPED` - the service is installed and can be started (needs elevation);
* :data:`MISSING` - iTunes has to be installed.

:func:`download_itunes` fetches Apple's current installer and refuses to hand back
anything that is not signed by Apple. Downloading and *running* it are deliberately
separate steps: the engine fetches and verifies, the desktop app launches - the same
split ``services/update_service.dart`` uses for iPASide's own updater.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

import requests

from . import doctor, paths
from .errors import EngineError

# Windows matches services on their own name rather than their display name, and
# this is it verbatim.
SERVICE_NAME = "Apple Mobile Device Service"

# The states :func:`status` reports. A vocabulary rather than a pair of booleans
# because each one has a different remedy, and a UI that cannot tell "stopped"
# from "never installed" offers the wrong button.
RUNNING = "running"
STOPPED = "stopped"
MISSING = "missing"
UNSUPPORTED = "unsupported"

# Apple's own redirector, which always resolves to the *current* installer (a 301
# to secure-appldnld.apple.com/itunes12/<build>/iTunes64Setup.exe). Deliberately
# not a pinned build URL: Apple's support pages still link a 2021 installer, so
# anything hardcoded here would ship something years stale to every user.
ITUNES_DOWNLOAD_URL = "https://www.apple.com/itunes/download/win64"

# Only the 64-bit installer exists as far as iPASide is concerned - the app itself
# is x64-only (`ArchitecturesAllowed=x64compatible` in packaging/iPASide.iss), so
# there is no platform on which a 32-bit download could be the right answer.
INSTALLER_NAME = "iTunes64Setup.exe"

# The organisation Authenticode must name as the signer. Checked against the
# subject's O= field, which is the identity the CA actually validates; CN is
# cosmetic and Apple has changed its form before.
APPLE_SIGNER_ORGANISATION = "Apple Inc."

# Where iTunes registers itself. Read only to make the message accurate ("iTunes
# is installed but its service is missing" reads very differently from "install
# iTunes"); the service state above is what decides anything.
_ITUNES_REGISTRY_KEY = r"SOFTWARE\Apple Computer, Inc.\iTunes"

# AMDS's own install directory, and the second signal that the Apple stack has
# been here: a repair install can leave this behind without the registry key.
_MOBILE_DEVICE_SUPPORT = ("Apple", "Mobile Device Support")

# 1 MiB reads: ~200 progress updates across a 198 MB download, which is a bar
# that moves without flooding the UI with frames.
_CHUNK_BYTES = 1 << 20

# (connect, read). The read timeout is per-chunk, not for the whole transfer, so
# it can be short enough to notice a dead connection on a download this size.
_TIMEOUTS = (20, 60)

# How long to wait for `sc start` to actually reach RUNNING. sc returns as soon as
# the service reports START_PENDING, so the state has to be polled afterwards;
# AMDS is up in well under a second, and this ceiling only bounds a sick one.
_START_TIMEOUT_SECONDS = 20.0
_START_POLL_SECONDS = 0.4

# Signature checking is bounded compute (about a second here); this only bounds a
# wedged PowerShell. The elevation window is longer because a person has to answer
# the UAC prompt - but it is still bounded, so an unanswered prompt cannot leave
# the engine waiting for the rest of the session.
_VERIFY_TIMEOUT_SECONDS = 120.0
_ELEVATION_TIMEOUT_SECONDS = 180.0

# ERROR_CANCELLED - what ShellExecute reports when the user dismisses the UAC
# prompt. Matched on the code rather than the message, which is localised.
_ERROR_CANCELLED = 1223

# (phase, percent, step-text) - the same callback shape `sideload` reports with, so
# the CLI's existing stderr progress writer and the app's existing progress parser
# both work on this unchanged.
ProgressFn = Callable[[str, Any, "str | None"], None]


class AppleSupportError(EngineError):
    """Apple's device stack could not be inspected, installed, or started."""


# --------------------------------------------------------------------------- #
# Status
# --------------------------------------------------------------------------- #
def status() -> dict[str, Any]:
    """Report the state of Apple's device stack on this machine.

    ``state`` is one of :data:`RUNNING`, :data:`STOPPED`, :data:`MISSING` or
    :data:`UNSUPPORTED`; ``detail`` is one sentence written to be shown verbatim.
    The remaining fields are the evidence behind them, so a support conversation
    does not have to guess what was actually looked at.
    """
    if os.name != "nt":
        return {
            "state": UNSUPPORTED,
            "service_name": SERVICE_NAME,
            "service_state": None,
            "itunes_installed": False,
            "itunes_version": None,
            "detail": (
                "Apple Mobile Device Service is Windows-only; on this host, "
                "usbmuxd has to be installed and running instead."
            ),
        }

    # doctor owns the service query so there is exactly one `sc query` in the
    # engine; two probes that can disagree is the whole problem this module fixes.
    service_state = doctor._windows_service_state(SERVICE_NAME)
    version = _itunes_version()
    installed = version is not None or _mobile_device_support_dir().is_dir()

    if service_state == "RUNNING":
        state = RUNNING
        detail = "Apple Mobile Device Service is running; USB device I/O is available."
    elif service_state is None:
        state = MISSING
        detail = (
            (
                "iTunes is installed but Apple Mobile Device Service is not present. "
                "Reinstalling iTunes restores it."
            )
            if installed
            else (
                "Apple Mobile Device Service is not installed, so iPASide cannot see "
                "any iPhone. It comes with iTunes."
            )
        )
    else:
        state = STOPPED
        detail = (
            f"Apple Mobile Device Service is installed but not running "
            f"(state={service_state}). Starting it needs administrator rights."
        )

    return {
        "state": state,
        "service_name": SERVICE_NAME,
        "service_state": service_state,
        "itunes_installed": installed,
        "itunes_version": version,
        "detail": detail,
    }


def _itunes_version() -> str | None:
    """iTunes' registered version, or None when it is not registered at all.

    Only the native 64-bit view is read. iPASide is an x64 application offering
    the x64 installer, so that is the install it can reason about; a machine with
    a 32-bit iTunes still gets its *service* state read correctly above, which is
    what every decision here actually turns on.
    """
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover - Windows-only import
        return None
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            _ITUNES_REGISTRY_KEY,
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            value, _kind = winreg.QueryValueEx(key, "Version")
    except OSError:
        # Key absent (iTunes was never installed) or unreadable; either way there
        # is no version to report, and the service state is the real answer.
        return None
    text = str(value).strip()
    return text or None


def _mobile_device_support_dir() -> Path:
    """``%CommonProgramFiles%\\Apple\\Mobile Device Support`` - where AMDS installs."""
    common = os.environ.get("CommonProgramFiles") or r"C:\Program Files\Common Files"
    return Path(common).joinpath(*_MOBILE_DEVICE_SUPPORT)


# --------------------------------------------------------------------------- #
# Download + verification
# --------------------------------------------------------------------------- #
def download_itunes(
    directory: str | None = None,
    *,
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """Download Apple's current iTunes installer, verify it, and return its path.

    Streams progress as ``("download", percent, step)`` and only returns once the
    file on disk has been proved to be Apple's - a caller that gets a path back is
    holding something safe to run. Anything else raises and leaves no file behind.

    Running the installer is not this function's job; see the module docstring.
    """
    if os.name != "nt":
        raise AppleSupportError("The iTunes installer is a Windows executable.")

    progress: ProgressFn = on_progress or (lambda *_args: None)
    target_dir = _download_dir(directory)
    destination = target_dir / INSTALLER_NAME

    # Written straight to its final name rather than to a staging file, because the
    # verification below is what publishes it: this function returns the path only
    # after the signature check passes, and deletes the file on every other path,
    # so an unverified download is never something a caller can be handed.
    progress("download", 0, "Contacting Apple\u2026")
    written, total = _stream_to_file(destination, progress)

    if total and written != total:
        # A truncated installer would fail its signature check anyway; saying it
        # ended early is a far more useful sentence than "not signed by Apple".
        _delete(destination)
        raise AppleSupportError(
            f"The iTunes download ended early ({_mb(written)} of {_mb(total)}) "
            "and was discarded. Check your connection and try again."
        )

    progress("download", 100, "Verifying Apple's signature\u2026")
    try:
        signature = verify_apple_signature(destination)
    except AppleSupportError:
        _delete(destination)
        raise

    return {
        "path": str(destination),
        "bytes": written,
        "url": ITUNES_DOWNLOAD_URL,
        "signer": signature["signer"],
        "signature_status": signature["status"],
    }


def _stream_to_file(destination: Path, progress: ProgressFn) -> tuple[int, int]:
    """Stream :data:`ITUNES_DOWNLOAD_URL` to ``destination``; return (written, total)."""
    try:
        response = requests.get(
            ITUNES_DOWNLOAD_URL,
            stream=True,
            timeout=_TIMEOUTS,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        raise AppleSupportError(
            "Could not reach Apple to download iTunes. Check your internet "
            "connection and try again."
        ) from exc

    with response:
        if response.status_code != 200:
            raise AppleSupportError(
                f"Apple's download server did not serve the iTunes installer "
                f"(HTTP {response.status_code}). Try again later."
            )

        total = _content_length(response)
        written = 0
        try:
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=_CHUNK_BYTES):
                    if not chunk:  # keep-alive chunks carry no payload
                        continue
                    handle.write(chunk)
                    written += len(chunk)
                    progress("download", _percent(written, total), _step(written, total))
        except requests.RequestException as exc:
            _delete(destination)
            raise AppleSupportError(
                f"The iTunes download failed after {_mb(written)} and was "
                "discarded. Check your connection and try again."
            ) from exc
        except OSError as exc:
            _delete(destination)
            raise AppleSupportError(
                f"Could not write the iTunes installer to {destination.parent}: "
                f"{exc.strerror or exc}"
            ) from exc

    return written, total


def verify_apple_signature(path: str | Path) -> dict[str, str]:
    """Prove ``path`` carries a valid Authenticode signature issued to Apple.

    Returns the signature status and signer subject; raises
    :class:`AppleSupportError` for anything else. **Fail-closed**: a signature that
    is absent, invalid, untrusted, or valid but issued to somebody other than
    Apple all raise, as does any inability to perform the check at all.

    Why a signature and not a checksum: Apple publishes no checksum for this
    installer, but the signature is the stronger proof regardless. A checksum only
    shows the bytes match a list we were handed - by the same server that handed us
    the bytes - whereas a valid Authenticode signature shows Apple's private key
    produced them, which no compromise of the download path can forge. That matters
    more here than almost anywhere else in iPASide: the thing being verified
    installs kernel-mode USB drivers and a system service.

    The verdict comes from Windows itself rather than from certificate parsing
    here, because WinVerifyTrust - reached through ``Get-AuthenticodeSignature`` -
    is the same authority that decides whether the OS trusts the binary, chain,
    trust store and all. One subprocess is a fine price for a once-per-machine
    action.
    """
    target = Path(path)
    signature_status, subject = _authenticode(target)

    if signature_status.casefold() != "valid":
        raise AppleSupportError(
            f"The downloaded iTunes installer is not validly signed "
            f"(Windows reports its signature as '{signature_status}'), so it was "
            "not installed. Try downloading it again."
        )

    organisations = _subject_field(subject, "O")
    if organisations != [APPLE_SIGNER_ORGANISATION]:
        raise AppleSupportError(
            f"The downloaded iTunes installer is signed by "
            f"'{subject or 'an unnamed signer'}', not by "
            f"{APPLE_SIGNER_ORGANISATION}, so it was not installed."
        )

    return {"status": signature_status, "signer": subject}


def _authenticode(path: Path) -> tuple[str, str]:
    """Ask Windows for ``path``'s signature status and signer subject."""
    if os.name != "nt":
        raise AppleSupportError(
            "Authenticode signatures can only be verified on Windows."
        )
    if not path.is_file():
        raise AppleSupportError(f"There is no file to verify at {path}.")

    # The path travels in the environment rather than inside the script text, so a
    # path containing a quote cannot end up as PowerShell to run. Both values are
    # emitted with a fixed prefix because `Write-Output $null` prints no line at
    # all, and an unsigned file has no signer - which would otherwise silently
    # turn a two-line answer into a one-line one.
    script = (
        "$ErrorActionPreference = 'Stop';"
        "$signature = Get-AuthenticodeSignature -LiteralPath $env:IPASIDE_VERIFY_PATH;"
        "Write-Output ('status=' + $signature.Status);"
        "Write-Output ('subject=' + $signature.SignerCertificate.Subject)"
    )

    try:
        proc = _run_powershell(
            script,
            timeout=_VERIFY_TIMEOUT_SECONDS,
            IPASIDE_VERIFY_PATH=str(path),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AppleSupportError(
            "Windows could not check the installer's signature, so it was not "
            f"installed ({exc})."
        ) from exc

    values = _tagged_lines(proc.stdout)
    if proc.returncode != 0 or "status" not in values:
        raise AppleSupportError(
            "Windows could not check the installer's signature, so it was not "
            f"installed ({_first_line(proc.stderr or proc.stdout)})."
        )
    return values["status"].strip(), values.get("subject", "").strip()


def _run_powershell(
    script: str,
    *,
    timeout: float,
    **variables: str,
) -> subprocess.CompletedProcess[str]:
    """Run ``script`` in Windows PowerShell, passing values in as env variables.

    ``PSModulePath`` is dropped rather than inherited. PowerShell 7 exports its own
    module search path, and a 5.1 child that inherits it looks for 5.1's built-in
    modules in 7's directories and finds none - which failed
    ``Get-AuthenticodeSignature`` with ``CouldNotAutoloadMatchingModule`` when the
    engine happened to be started from a ``pwsh`` session. Unsetting it lets each
    PowerShell compute its own default, so the verification does not depend on
    which shell the app was launched from.
    """
    environment = {
        key: value for key, value in os.environ.items() if key.upper() != "PSMODULEPATH"
    }
    environment.update(variables)
    return subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
    )


def _powershell() -> str:
    """The absolute path to Windows PowerShell.

    Absolute on purpose. Launching ``powershell`` by name would let anything
    earlier on PATH answer for Windows about whether a kernel-driver installer is
    signed by Apple, which turns the check into theatre.
    """
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    exe = Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not exe.is_file():
        raise AppleSupportError(
            f"Windows PowerShell was not found at {exe}, so the installer's "
            "signature could not be verified."
        )
    return str(exe)


def _tagged_lines(output: str) -> dict[str, str]:
    """Parse ``key=value`` lines from a helper script's stdout (first key wins)."""
    values: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values.setdefault(key.strip(), value)
    return values


def _subject_field(subject: str, name: str) -> list[str]:
    """Every value of one RDN in an X.500 subject, e.g. ``O`` -> ``['Apple Inc.']``.

    A list rather than a single value so the caller can insist on exactly one: a
    subject carrying two organisations is not something to pick a winner from.
    Values may be quoted when they contain a comma (``O="DigiCert, Inc."``), so the
    split honours quoting instead of naively cutting on every comma - and matching
    the whole RDN rather than searching the subject for ``O=Apple Inc.`` is what
    stops a signer from smuggling that text through a field it does not own.
    """
    wanted = name.casefold()
    found: list[str] = []
    for part in _split_rdns(subject):
        key, separator, value = part.partition("=")
        if not separator or key.strip().casefold() != wanted:
            continue
        text = value.strip()
        if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        found.append(text)
    return found


def _split_rdns(subject: str) -> list[str]:
    """Split a subject on its commas, ignoring commas inside quoted values."""
    parts: list[str] = []
    current: list[str] = []
    quoted = False
    for char in subject:
        if char == '"':
            quoted = not quoted
            current.append(char)
        elif char == "," and not quoted:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [part for part in parts if part.strip()]


# --------------------------------------------------------------------------- #
# Starting the service
# --------------------------------------------------------------------------- #
def start_service() -> dict[str, Any]:
    """Start the Apple Mobile Device Service, asking Windows for elevation.

    Starting a Windows service needs administrator rights, which iPASide does not
    have and should not run with. So the request is escalated the way Windows
    intends - ``Start-Process -Verb RunAs``, i.e. a UAC prompt the user answers -
    and declining it is a normal outcome rather than a failure: ``started`` is
    False, ``reason`` says ``elevation_declined``, and nothing was changed.

    Always reports the freshly re-read :func:`status` alongside, so a caller never
    has to guess whether the state it is showing survived the attempt.
    """
    if os.name != "nt":
        raise AppleSupportError(
            "Apple Mobile Device Service is a Windows service; there is nothing "
            "to start on this host."
        )

    current = status()
    if current["state"] == RUNNING:
        # Nothing to elevate for. Worth checking first rather than prompting and
        # then reporting sc's "service is already running" as a failure.
        return _start_result(True, "already_running", current["detail"], current)
    if current["state"] == MISSING:
        raise AppleSupportError(
            "There is no Apple Mobile Device Service to start on this machine; "
            "install iTunes first."
        )

    outcome, code, message = _elevated_service_start()
    if outcome == "cancelled":
        return _start_result(
            False,
            "elevation_declined",
            "Starting Apple Mobile Device Service needs administrator rights, "
            "and the request was declined. Nothing was changed.",
            status(),
        )
    if outcome != "ok":
        return _start_result(
            False,
            "failed",
            "Windows would not start Apple Mobile Device Service"
            f"{f' ({message})' if message else ''}. You can start it from "
            "Services, or reinstall iTunes.",
            status(),
        )

    if _await_running():
        after = status()
        return _start_result(True, "started", after["detail"], after)

    after = status()
    return _start_result(
        False,
        "did_not_start",
        "Apple Mobile Device Service was asked to start but did not come up"
        f"{f' (sc exit code {code})' if code else ''}. Reinstalling iTunes "
        "usually repairs it.",
        after,
    )


def _start_result(
    started: bool,
    reason: str,
    detail: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    return {"started": started, "reason": reason, "detail": detail, "status": state}


def _elevated_service_start() -> tuple[str, int | None, str]:
    """Run ``sc start`` elevated; return (outcome, sc exit code, message).

    ``outcome`` is ``ok`` once the elevated process ran (whatever sc then made of
    it), ``cancelled`` when the UAC prompt was declined, or ``error``.
    """
    script = (
        "$ErrorActionPreference = 'Stop';"
        "try {"
        " $p = Start-Process -FilePath $env:IPASIDE_SC_EXE"
        " -ArgumentList $env:IPASIDE_SC_ARGS -Verb RunAs -Wait -PassThru"
        " -WindowStyle Hidden;"
        " Write-Output 'outcome=ok';"
        " Write-Output ('code=' + $p.ExitCode)"
        "} catch {"
        " Write-Output 'outcome=error';"
        " Write-Output ('code=' + $_.Exception.NativeErrorCode);"
        " Write-Output ('message=' + $_.Exception.Message)"
        "}"
    )

    try:
        proc = _run_powershell(
            script,
            timeout=_ELEVATION_TIMEOUT_SECONDS,
            # One pre-quoted argument string: the service name contains spaces, and
            # PowerShell passes an -ArgumentList through verbatim only when it is a
            # single string - which is what makes
            # `sc start "Apple Mobile Device Service"` arrive intact.
            IPASIDE_SC_EXE=_system32("sc.exe"),
            IPASIDE_SC_ARGS=f'start "{SERVICE_NAME}"',
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "error", None, str(exc)

    values = _tagged_lines(proc.stdout)
    code = _as_int(values.get("code"))
    message = values.get("message", "").strip()
    if values.get("outcome") == "ok":
        return "ok", code, message
    if code == _ERROR_CANCELLED:
        return "cancelled", code, message
    if values.get("outcome") == "error":
        return "error", code, message
    return "error", None, _first_line(proc.stderr or proc.stdout)


def _await_running() -> bool:
    """Poll the service until it reports RUNNING, or give up.

    ``sc start`` returns the moment the service accepts START_PENDING, so the call
    returning says nothing about whether it came up.
    """
    deadline = time.monotonic() + _START_TIMEOUT_SECONDS
    while True:
        if doctor._windows_service_state(SERVICE_NAME) == "RUNNING":
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(_START_POLL_SECONDS)


def _system32(name: str) -> str:
    """An absolute path into System32, for the same reason as :func:`_powershell`."""
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    return str(Path(root) / "System32" / name)


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _download_dir(directory: str | None) -> Path:
    """Where the installer is written: the caller's folder, or the app's own.

    A blank string counts as unset - a UI that keeps a folder as a string sends ""
    when the user has not chosen one, and resolving that would quietly mean
    whatever directory the engine happens to be running in.
    """
    if not directory or not directory.strip():
        return paths.downloads_dir()
    target = Path(directory).expanduser().resolve()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AppleSupportError(
            f"Cannot use '{directory}' for the download: {exc.strerror or exc}"
        ) from exc
    return target


def _content_length(response: requests.Response) -> int:
    """The response's byte count, or 0 when the server did not commit to one."""
    raw = response.headers.get("Content-Length")
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if value > 0 else 0


def _percent(written: int, total: int) -> int | None:
    """0-100 against a known total; None while the total is unknown."""
    if total <= 0:
        return None
    return min(100, round(written * 100 / total))


def _step(written: int, total: int) -> str:
    if total <= 0:
        return "Downloading iTunes\u2026"
    return f"Downloading iTunes \u00b7 {_mb(written)} of {_mb(total)}"


def _mb(count: int) -> str:
    return f"{count / (1 << 20):.1f} MB"


def _first_line(output: str) -> str:
    """The first meaningful line of a PowerShell failure, for one-sentence reporting.

    PowerShell spreads one error over several lines and ends with its own
    decoration (``+ CategoryInfo``, ``+ FullyQualifiedErrorId``); the first line is
    the sentence that says what went wrong, so that is the one worth quoting.
    """
    for line in output.splitlines():
        text = line.strip()
        if text and not text.startswith("+"):
            return text[:200]
    return "no answer from PowerShell"


def _as_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _delete(path: Path) -> None:
    """Remove a download we are refusing to hand back, best effort.

    Best effort is enough: nothing is ever run from a path this module did not
    return, and it only returns one that verified.
    """
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
