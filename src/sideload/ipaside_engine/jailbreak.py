"""Jailbreak advisor + installer (Dopamine).

iPASide is a sideloader, not a jailbreak: it never runs an exploit. What it *can* do
is the two things it already does for every other IPA — tell the user whether a tool
fits their device, and sign + install that tool's app over USB. The exploit itself
runs on the phone afterwards, exactly as if the user had sideloaded Dopamine by hand.

Two responsibilities live here:

* **Advise.** From the connected device's ``ProductType`` (e.g. ``iPhone12,1``),
  ``ProductVersion`` (e.g. ``16.7.15``), and ``BuildVersion`` when a beta must be
  distinguished from its final release, work out whether Dopamine supports it.

  The compatibility data is **not** baked into this build. It is fetched at runtime from
  :data:`COMPAT_URL` (a JSON file in the iPASide repo), so when Dopamine adds a new iOS
  version — or a new device — the fix is a one-line edit to that file, committed once,
  and every existing iPASide install picks it up. There is deliberately no bundled
  fallback: if the list cannot be fetched, the caller is told to retry rather than shown
  a stale answer.

* **Install.** Fetch the *latest* ``Dopamine.ipa`` from opa334's GitHub releases (never a
  pinned version) and hand it to :func:`ipaside_engine.sideload.run_sideload`, the same
  provision → sign → install path a normal sideload uses. Auto-refresh then keeps it
  alive like any other sideloaded app.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import requests

from . import ipa as ipa_module

# (phase, percent, step) - the same shape sideload/livecontainer report.
ProgressFn = Callable[[str, Any, "str | None"], None]

_TIMEOUTS = (20, 60)
_CHUNK_BYTES = 1 << 20


class JailbreakError(Exception):
    """A jailbreak could not be advised on or installed."""


# --------------------------------------------------------------------------- #
# The tool
# --------------------------------------------------------------------------- #
#: Static metadata for the one jailbreak iPASide offers. Its name and home page do not
#: go stale, so they stay in code; only the *compatibility* (which devices, which iOS)
#: is fetched live - see :func:`fetch_compat`.
TOOL: dict[str, Any] = {
    "id": "dopamine",
    "name": "Dopamine",
    "kind": "Semi-untethered \u00b7 rootless",
    "developer": "opa334 (Lars Fr\u00f6der)",
    "project_url": "https://github.com/opa334/Dopamine",
}

#: opa334's release feed. Always the *latest* release - iPASide never pins a version.
RELEASES_URL = "https://api.github.com/repos/opa334/Dopamine/releases/latest"

#: Where the compatibility list lives. Fetched fresh on every advise so support for a
#: newly jailbreakable iOS reaches users by editing this file, not by shipping an app.
COMPAT_URL = (
    "https://raw.githubusercontent.com/pwnapplehat/iPASide/main/compat/dopamine.json"
)


# --------------------------------------------------------------------------- #
# The live compatibility list
# --------------------------------------------------------------------------- #
def fetch_compat() -> dict[str, Any]:
    """Fetch and validate the Dopamine compatibility list from :data:`COMPAT_URL`.

    Returns the parsed document (``devices`` / ``support`` / ``no_jailbreak`` / ``tool``).
    Raises :class:`JailbreakError` on any network, decode, or shape problem - there is no
    bundled fallback, so the caller shows a retry rather than a stale answer.
    """
    try:
        response = requests.get(COMPAT_URL, timeout=_TIMEOUTS)
        response.raise_for_status()
        document = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise JailbreakError(
            "Couldn't fetch the jailbreak compatibility list. Check your internet "
            "connection and try again."
        ) from exc

    if not _valid_compat_document(document):
        raise JailbreakError(
            "The jailbreak compatibility list was malformed. Try again shortly."
        )
    return document


def chip_for(compat: dict[str, Any], product_type: str | None) -> str | None:
    """The chip family for a ``ProductType`` per the compat list, or None if unlisted."""
    if not product_type:
        return None
    entry = compat.get("devices", {}).get(product_type)
    if isinstance(entry, dict):
        chip = entry.get("chip")
        return chip if isinstance(chip, str) else None
    return None


def device_name_for(compat: dict[str, Any], product_type: str | None) -> str | None:
    """A marketing name for a ``ProductType`` per the compat list, when it carries one."""
    if not product_type:
        return None
    entry = compat.get("devices", {}).get(product_type)
    if isinstance(entry, dict):
        name = entry.get("name")
        return name if isinstance(name, str) else None
    return None


def parse_version(value: str | None) -> tuple[int, int, int] | None:
    """Parse ``16.7.15`` / ``26.0`` / ``18`` into a 3-tuple, padding missing parts."""
    if not value:
        return None
    parts = str(value).strip().split(".")
    numbers: list[int] = []
    for index in range(3):
        if index < len(parts):
            try:
                numbers.append(int(parts[index]))
            except ValueError:
                return None
        else:
            numbers.append(0)
    return (numbers[0], numbers[1], numbers[2])


def _valid_ranges(value: Any) -> bool:
    """Whether a remote range list is ordered, non-overlapping, and parseable."""
    if not isinstance(value, list):
        return False
    previous_high: tuple[int, int, int] | None = None
    for pair in value:
        if not isinstance(pair, list) or len(pair) != 2:
            return False
        low = parse_version(pair[0]) if isinstance(pair[0], str) else None
        high = parse_version(pair[1]) if isinstance(pair[1], str) else None
        if low is None or high is None or low > high:
            return False
        if previous_high is not None and previous_high >= low:
            return False
        previous_high = high
    return True


def _string_list(value: Any) -> list[str] | None:
    """A validated list of non-empty strings, or None for the wrong shape."""
    if not isinstance(value, list) or not all(
        isinstance(item, str) and bool(item) for item in value
    ):
        return None
    return value


def _valid_build_rules(
    value: Any, known_chips: set[str], known_devices: set[str]
) -> bool:
    """Validate exact-build selectors and reject ambiguous duplicate rules."""
    if not isinstance(value, list):
        return False
    seen: set[tuple[str, str]] = set()
    for rule in value:
        if not isinstance(rule, dict):
            return False
        version = rule.get("product_version")
        build = rule.get("build")
        label = rule.get("label")
        chips = _string_list(rule.get("chips", []))
        devices = _string_list(rule.get("devices", []))
        excluded = _string_list(rule.get("exclude_devices", []))
        if (
            not isinstance(version, str)
            or parse_version(version) is None
            or not isinstance(build, str)
            or not build
            or not isinstance(label, str)
            or not label
            or chips is None
            or devices is None
            or excluded is None
            or not (chips or devices)
            or not set(chips) <= known_chips
            or not set(devices) <= known_devices
            or not set(excluded) <= known_devices
            or (version, build.casefold()) in seen
        ):
            return False
        seen.add((version, build.casefold()))
    return True


def _valid_compat_document(document: Any) -> bool:
    """Validate schema 3 before any remote rule can influence install gating."""
    if not isinstance(document, dict) or document.get("schema") != 3:
        return False
    support = document.get("support")
    devices = document.get("devices")
    no_jailbreak = _string_list(document.get("no_jailbreak"))
    if not isinstance(support, dict) or not isinstance(devices, dict):
        return False
    if no_jailbreak is None:
        return False
    if not all(
        isinstance(chip, str) and bool(chip) and _valid_ranges(ranges)
        for chip, ranges in support.items()
    ):
        return False

    known_chips = set(support) | set(no_jailbreak)
    for product_type, entry in devices.items():
        if (
            not isinstance(product_type, str)
            or not product_type
            or not isinstance(entry, dict)
            or entry.get("chip") not in known_chips
            or not isinstance(entry.get("name"), str)
            or not entry["name"]
            or ("support" in entry and not _valid_ranges(entry["support"]))
        ):
            return False
    return _valid_build_rules(
        document.get("build_support"), known_chips, set(devices)
    )


def _format_version(version: tuple[int, int, int]) -> str:
    """Render a version tuple, dropping a trailing zero patch (26.0.0 -> 26.0)."""
    major, minor, patch = version
    return f"{major}.{minor}" if patch == 0 else f"{major}.{minor}.{patch}"


def _ranges_for(
    compat: dict[str, Any], chip: str, product_type: str | None = None
) -> list[tuple[tuple[int, int, int], tuple[int, int, int]]]:
    """The parsed (min, max) ranges for a device, falling back to its chip.

    Most devices use the chip-wide ``support`` table. A device may carry its own
    ``support`` list when two products with the same chip cannot run the same OS
    generations (A12 iPhones stop at iOS 18 while A12 iPads run iPadOS 26).
    A malformed pair is skipped rather than raising: one bad remote entry must not
    take down the whole advisor.
    """
    pairs: Any = compat.get("support", {}).get(chip, [])
    if product_type:
        entry = compat.get("devices", {}).get(product_type)
        if isinstance(entry, dict) and "support" in entry:
            pairs = entry.get("support")

    if not isinstance(pairs, (list, tuple)):
        return []

    parsed: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = []
    for pair in pairs:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        low = parse_version(str(pair[0]))
        high = parse_version(str(pair[1]))
        if low is not None and high is not None:
            parsed.append((low, high))
    return parsed


def _has_device_support_override(
    compat: dict[str, Any], product_type: str | None
) -> bool:
    """Whether a device deliberately replaces its chip-wide numeric ranges."""
    if not product_type:
        return False
    entry = compat.get("devices", {}).get(product_type)
    return isinstance(entry, dict) and "support" in entry


def _build_rules_for(
    compat: dict[str, Any], chip: str, product_type: str | None
) -> list[tuple[tuple[int, int, int], str, str]]:
    """Exact beta-build rules applying to this chip or ProductType.

    Each tuple is ``(ProductVersion, BuildVersion, display label)``. Exact builds
    are intentionally separate from numeric ranges: treating ``26.1 beta 3`` as
    all of ``26.1`` would incorrectly accept the patched final release.
    """
    raw_rules = compat.get("build_support")
    if not isinstance(raw_rules, list):
        return []

    parsed: list[tuple[tuple[int, int, int], str, str]] = []
    for rule in raw_rules:
        if not isinstance(rule, dict):
            continue
        chips = rule.get("chips")
        devices = rule.get("devices")
        excluded_devices = rule.get("exclude_devices")
        selected = (
            isinstance(chips, list) and chip in chips
        ) or (
            product_type is not None
            and isinstance(devices, list)
            and product_type in devices
        )
        excluded = (
            product_type is not None
            and isinstance(excluded_devices, list)
            and product_type in excluded_devices
        )
        applies = selected and not excluded
        version_text = rule.get("product_version")
        if not isinstance(version_text, str):
            continue
        version = parse_version(version_text)
        build = rule.get("build")
        label = rule.get("label")
        if applies and version is not None and isinstance(build, str) and build:
            display_label = (
                label if isinstance(label, str) and label else version_text
            )
            parsed.append(
                (version, build, display_label)
            )
    return parsed


def _support_ceiling(
    ranges: list[tuple[tuple[int, int, int], tuple[int, int, int]]],
    build_rules: list[tuple[tuple[int, int, int], str, str]],
) -> tuple[tuple[int, int, int], str] | None:
    """Highest supported release/beta and the exact label the UI should show."""
    candidates = [(high, _format_version(high)) for _low, high in ranges]
    candidates.extend((version, label) for version, _build, label in build_rules)
    ceiling: tuple[tuple[int, int, int], str] | None = None
    for candidate in candidates:
        if ceiling is None or candidate[0] >= ceiling[0]:
            ceiling = candidate
    return ceiling


# Advisor outcomes.
SUPPORTED = "supported"
UNSUPPORTED_VERSION = "unsupported_version"
NO_JAILBREAK = "no_jailbreak"
UNKNOWN_DEVICE = "unknown_device"


def advise(
    product_type: str | None,
    product_version: str | None,
    compat: dict[str, Any],
    build_version: str | None = None,
) -> dict[str, Any]:
    """Whether Dopamine fits the given device, and why, against a fetched compat list.

    Returns a dict the UI renders directly: the resolved chip and device name, the
    running iOS, an ``outcome`` from the constants above, a one-line human ``summary``,
    and ``can_install`` (true only when the outcome is :data:`SUPPORTED`).
    """
    chip = chip_for(compat, product_type)
    name = device_name_for(compat, product_type) or product_type
    running = parse_version(product_version)
    tool = {**TOOL, **(compat.get("tool") if isinstance(compat.get("tool"), dict) else {})}
    no_jailbreak = compat.get("no_jailbreak") or []

    result: dict[str, Any] = {
        "tool": tool,
        "product_type": product_type,
        "device_name": name,
        "chip": chip,
        "ios_version": product_version,
        "build_version": build_version,
        "can_install": False,
    }

    if chip is None:
        result["outcome"] = UNKNOWN_DEVICE
        result["summary"] = (
            f"Could not identify {product_type or 'this device'} in the compatibility "
            f"list. Check {tool['name']}'s supported devices on its project page."
        )
        return result

    if chip in no_jailbreak:
        result["outcome"] = NO_JAILBREAK
        result["summary"] = (
            f"{name} uses the {chip} chip, which has no public jailbreak yet \u2014 "
            f"{tool['name']} does not support it."
        )
        return result

    ranges = _ranges_for(compat, chip, product_type)
    build_rules = _build_rules_for(compat, chip, product_type)
    ceiling = _support_ceiling(ranges, build_rules)
    if ceiling is None and _has_device_support_override(compat, product_type):
        result["outcome"] = UNSUPPORTED_VERSION
        result["summary"] = (
            f"{name} ({chip}) cannot run an iOS or iPadOS version supported by "
            f"{tool['name']}."
        )
        return result
    if ceiling is None:
        result["outcome"] = UNKNOWN_DEVICE
        result["summary"] = (
            f"Could not determine {tool['name']} support for the {chip} chip. Check its "
            "supported devices on the project page."
        )
        return result

    ceiling_version, ceiling_text = ceiling
    result["max_supported"] = ceiling_text

    if running is None:
        result["outcome"] = UNKNOWN_DEVICE
        result["summary"] = (
            f"{name} ({chip}) is supported up to iOS {ceiling_text}, but its current "
            "iOS version could not be read."
        )
        return result

    matched_build_label = None
    if isinstance(build_version, str):
        matched_build_label = next(
            (
                label
                for version, supported, label in build_rules
                if running == version
                and build_version.casefold() == supported.casefold()
            ),
            None,
        )
    if (
        any(low <= running <= high for low, high in ranges)
        or matched_build_label is not None
    ):
        running_text = matched_build_label or product_version
        result["outcome"] = SUPPORTED
        result["can_install"] = True
        result["summary"] = (
            f"{name} ({chip}) on iOS {running_text} is supported by {tool['name']} "
            f"(up to iOS {ceiling_text})."
        )
        return result

    result["outcome"] = UNSUPPORTED_VERSION
    if running > ceiling_version:
        result["summary"] = (
            f"{name} ({chip}) on iOS {product_version} is too new for {tool['name']} \u2014 "
            f"it supports up to iOS {ceiling_text} on this chip."
        )
    else:
        result["summary"] = (
            f"iOS {product_version} is not in {tool['name']}'s supported range for "
            f"{name} ({chip}); it covers up to iOS {ceiling_text} on this chip."
        )
    return result


# --------------------------------------------------------------------------- #
# Getting the IPA
# --------------------------------------------------------------------------- #
def latest_release() -> dict[str, Any]:
    """Describe Dopamine's newest release, without downloading it."""
    try:
        response = requests.get(RELEASES_URL, timeout=_TIMEOUTS)
        response.raise_for_status()
        release = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise JailbreakError(
            "Could not reach GitHub to check for the latest Dopamine release. Check "
            f"your connection, or download the IPA yourself from {TOOL['project_url']}."
        ) from exc

    asset = _pick_asset(release.get("assets") or [])
    if asset is None:
        raise JailbreakError(
            f"Dopamine {release.get('tag_name') or 'latest'} has no .ipa attached. "
            f"Download it from {TOOL['project_url']}/releases and pick the file."
        )
    return {
        "version": release.get("tag_name"),
        "name": release.get("name"),
        "published_at": release.get("published_at"),
        "notes_url": release.get("html_url"),
        "asset_name": asset.get("name"),
        "url": asset.get("browser_download_url"),
        "bytes": asset.get("size"),
    }


def _pick_asset(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Choose ``Dopamine.ipa`` from a release's assets.

    Only a plain ``.ipa`` is usable: the ``.tipa`` is for TrollStore (which iPASide
    cannot enable), so it is skipped rather than downloaded and then found unusable.
    Shortest matching name wins, so ``Dopamine.ipa`` beats any decorated variant.
    """
    candidates = [
        a for a in assets
        if str(a.get("name", "")).lower().endswith(".ipa")
        and not str(a.get("name", "")).lower().endswith(".tipa")
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda a: len(str(a.get("name", ""))))


def download(
    directory: str | None = None, *, on_progress: ProgressFn | None = None
) -> dict[str, Any]:
    """Download the latest Dopamine IPA and return where it landed."""
    from . import paths

    progress: ProgressFn = on_progress or (lambda *_args: None)
    release = latest_release()

    target_dir = Path(directory).expanduser().resolve() if directory else paths.downloads_dir()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise JailbreakError(f"Cannot write to {target_dir}: {exc.strerror or exc}") from exc
    destination = target_dir / str(release["asset_name"])

    progress("download", 0, f"Downloading Dopamine {release['version']}\u2026")
    written = _stream(str(release["url"]), destination, release.get("bytes") or 0, progress)

    expected = release.get("bytes") or 0
    if expected and written != expected:
        destination.unlink(missing_ok=True)
        raise JailbreakError(
            f"The Dopamine download ended early ({written} of {expected} bytes) and was "
            "discarded. Check your connection and try again."
        )

    # Confirm the download is a real app bundle before handing the path back - but do
    # NOT gate on the bundle id. Dopamine's own identifier is `com.opa334.FuckYou`
    # (opa334's deliberate choice), so matching the string "dopamine" would reject the
    # genuine article. Authenticity comes from the source: the official
    # opa334/Dopamine release asset fetched over HTTPS, not from the id.
    info = ipa_module.inspect(str(destination))
    if not str(info.get("bundle_id") or "").strip():
        destination.unlink(missing_ok=True)
        raise JailbreakError(
            f"{release['asset_name']} did not look like an app bundle. The release "
            "layout may have changed; download it yourself and pick the file, or try "
            "again."
        )

    return {**release, "path": str(destination), "bytes_written": written}


def _stream(url: str, destination: Path, total: int, progress: ProgressFn) -> int:
    try:
        response = requests.get(url, stream=True, timeout=_TIMEOUTS, allow_redirects=True)
    except requests.RequestException as exc:
        raise JailbreakError(
            "Could not download Dopamine. Check your internet connection."
        ) from exc

    with response:
        if response.status_code != 200:
            raise JailbreakError(
                f"GitHub did not serve the Dopamine IPA (HTTP {response.status_code})."
            )
        written = 0
        try:
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=_CHUNK_BYTES):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    written += len(chunk)
                    percent = round(written * 100 / total) if total else None
                    progress("download", percent, _downloaded_step(written, total))
        except (requests.RequestException, OSError) as exc:
            destination.unlink(missing_ok=True)
            raise JailbreakError(
                f"The Dopamine download failed after {written} bytes and was discarded."
            ) from exc
    return written


def _downloaded_step(written: int, total: int) -> str:
    mb = 1 << 20
    if total:
        return f"Downloading Dopamine \u00b7 {written // mb} / {total // mb} MB"
    return f"Downloading Dopamine \u00b7 {written // mb} MB"


# --------------------------------------------------------------------------- #
# Installing it
# --------------------------------------------------------------------------- #
def install(
    udid: str | None = None,
    *,
    ipa_path: str | None = None,
    keep_signed: bool = False,
    signed_dir: str | None = None,
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """Sign and install Dopamine, downloading the latest IPA if none is given.

    This is an ordinary sideload: iPASide provisions with the user's free Apple ID,
    signs, and installs over USB. The jailbreak exploit runs on the phone the first time
    the user opens Dopamine - iPASide never runs it. The install is recorded for
    auto-refresh like any other app, so its 7-day free-account profile is renewed.
    """
    from . import sideload  # imported here to avoid a cycle at module load

    progress: ProgressFn = on_progress or (lambda *_args: None)

    path = ipa_path
    downloaded: dict[str, Any] | None = None
    if not path:
        downloaded = download(on_progress=progress)
        path = downloaded["path"]

    # Its extensions are kept: unlike an ordinary free-account sideload we do not strip,
    # because there is no benefit to rewriting a single-binary jailbreak app and doing so
    # only adds a way to break it. FairPlay and platform checks still apply inside.
    result = sideload.run_sideload(
        path,
        udid,
        remove_extensions=False,
        remove_uisd=False,
        keep_signed=keep_signed,
        signed_dir=signed_dir,
        on_progress=progress,
    )

    return {
        **result,
        "tool": TOOL["id"],
        "dopamine_version": (downloaded or {}).get("version"),
    }
