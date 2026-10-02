"""Hardened WorkSlop Desktop update checker (Wave 10).

Checks the user's own GitHub repo (``adnan120hz/WorkSlop-Desktop-Version``)
for a newer release. Design rules (buildspec R6 §4):

* Channels are internal enums ``stable`` (non-prerelease releases only)
  and ``beta`` (all non-draft releases). A tag that *parses* as a
  prerelease can never enter the stable channel, even when GitHub's
  prerelease flag is wrong.
* Tags are validated: exactly one leading ``v`` is stripped, and the
  result must parse with ``packaging.version.Version``. Invalid tags are
  skipped and counted, never guessed at.
* Outcomes are structured: ``update_available`` / ``up_to_date`` /
  ``unknown``. ``unknown`` (network/timeout/HTTP/JSON errors) never
  produces a dialog and is never logged as "no update".
* Successful selections are cached per channel for 6 hours; ``unknown``
  results are not cached; ``force=True`` bypasses the cache.
* Exactly one structured log line per check; no headers, tokens, or
  response bodies are ever logged or sent. No auth token is sent.

Plain module, no Qt imports (imported by headless code); the Settings
helpers import lazily.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import requests
from packaging.version import InvalidVersion, Version

log = logging.getLogger("WorkSlop.update_check")

WORKSLOP_REPO = "adnan120hz/WorkSlop-Desktop-Version"
WORKSLOP_RELEASES_API = f"https://api.github.com/repos/{WORKSLOP_REPO}/releases"
WORKSLOP_LATEST_URL = f"https://github.com/{WORKSLOP_REPO}/releases/latest"

# Deprecated alias (existing imports keep working). The historical value
# pointed at the pre-rename repo name; it now carries the canonical repo.
Nugget_Repo = f"{WORKSLOP_REPO}/releases/latest"

CHANNEL_STABLE = "stable"
CHANNEL_BETA = "beta"
CHANNELS = (CHANNEL_STABLE, CHANNEL_BETA)

# User-facing channel labels. Never claim a stable public release.
CHANNEL_LABELS = {
    CHANNEL_STABLE: "Release",
    CHANNEL_BETA: "All releases",
}

_CACHE_TTL_SECONDS = 6 * 60 * 60
_MAX_PAGES = 10

# {channel: (monotonic_ts, ReleaseInfo)} — successful selections only.
_release_cache: dict = {}


@dataclass(frozen=True)
class ReleaseInfo:
    tag_name: str            # as published, e.g. "v10.0-pre"
    version: str             # stripped tag, e.g. "10.0-pre"
    name: str | None
    html_url: str
    prerelease: bool         # effective: GitHub flag OR parsed prerelease
    draft: bool
    published_at: str | None
    channel: str             # the channel this release was selected for
    assets: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class UpdateCheckResult:
    outcome: str             # "update_available" | "up_to_date" | "unknown"
    channel: str
    current_version: str
    current_build: int
    latest: ReleaseInfo | None
    error_kind: str | None   # network|timeout|http_<code>|rate_limited|
                             # invalid_json|no_releases|no_valid_tags|
                             # local_version_invalid
    checked_at: str


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_channel(channel) -> str:
    return channel if channel in CHANNELS else CHANNEL_STABLE


def default_channel(current_version: str, current_build: int) -> str:
    """Developer/prerelease installs hear about prereleases; final
    installs do not."""
    try:
        if Version(str(current_version)).is_prerelease or int(current_build) > 0:
            return CHANNEL_BETA
    except Exception:
        pass
    return CHANNEL_STABLE


def get_update_channel() -> str:
    """Persisted user channel (Settings key ``update_channel``), falling
    back to the version-derived default. A user choice always wins."""
    try:
        from src.controllers.settings import Settings
        from src.version import App_Version, App_Build
        stored = Settings("settings").value("update_channel", None)
        if stored in CHANNELS:
            return stored
        return default_channel(App_Version, App_Build)
    except Exception:
        return CHANNEL_STABLE


def set_update_channel(channel: str) -> None:
    try:
        from src.controllers.settings import Settings
        settings = Settings("settings")
        settings.setValue("update_channel", normalize_channel(channel))
        settings.sync()
    except Exception as e:
        log.warning("Could not persist update channel: %s", e)


def _strip_one_v(tag: str):
    stripped = tag[1:] if tag.startswith("v") else tag
    return stripped


def _public_version(value) -> "Version | None":
    """Parse a version for comparison, robust to release-tag shapes.

    One leading ``v`` is stripped and any ``+build`` local suffix is
    ignored (so a packaged ``10.0+0`` never compares newer than the
    ``v10.0`` release, and equal versions are simply equal — the
    "always says update is available" bug). Returns None when the value
    does not parse as a version at all.
    """
    try:
        raw = str(value or "").strip()
    except Exception:
        return None
    raw = _strip_one_v(raw)
    raw = raw.split("+", 1)[0]
    try:
        return Version(raw)
    except InvalidVersion:
        return None


def _parse_release(raw, channel: str):
    """Return ``(ReleaseInfo|None, invalid_tag: bool)`` for one API object."""
    if not isinstance(raw, dict):
        return None, False
    if raw.get("draft"):
        return None, False
    tag = raw.get("tag_name")
    if not isinstance(tag, str) or not tag:
        log.warning("Release %s has no usable tag_name; skipped",
                    raw.get("id"))
        return None, True
    version_str = _strip_one_v(tag)
    # packaging.Version silently accepts a leading "v" (PEP 440), but the
    # spec contract is: strip exactly one "v", and what remains must start
    # with a digit — "vv10.0" stays invalid, never becomes "10.0".
    if not version_str or not version_str[0].isdigit():
        return None, True
    try:
        parsed = Version(version_str)
    except InvalidVersion:
        return None, True
    effective_prerelease = bool(raw.get("prerelease")) or parsed.is_prerelease
    assets = tuple(
        {"name": a.get("name"),
         "browser_download_url": a.get("browser_download_url"),
         "size": a.get("size")}
        for a in (raw.get("assets") or []) if isinstance(a, dict))
    return ReleaseInfo(
        tag_name=tag,
        version=version_str,
        name=raw.get("name"),
        html_url=raw.get("html_url") or WORKSLOP_LATEST_URL,
        prerelease=effective_prerelease,
        draft=False,
        published_at=raw.get("published_at"),
        channel=channel,
        assets=assets,
    ), False


def _select(candidates: list):
    """Highest Version wins; ties break by later published_at, then by
    lexicographically larger tag_name (deterministic, order-free)."""
    if not candidates:
        return None
    return max(candidates, key=lambda r: (
        Version(r.version), r.published_at or "", r.tag_name))


def _fetch_releases():
    """Return ``(raw_list, error_kind)`` — exactly one is meaningful."""
    raw_all = []
    url = WORKSLOP_RELEASES_API
    params = {"per_page": 100}
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    for _page in range(_MAX_PAGES):
        try:
            response = requests.get(url, params=params, headers=headers,
                                    timeout=5)
        except requests.Timeout:
            return None, "timeout"
        except requests.RequestException:
            return None, "network"
        if response.status_code != 200:
            if (response.status_code == 403
                    and response.headers.get("X-RateLimit-Remaining") == "0"):
                return None, "rate_limited"
            return None, f"http_{response.status_code}"
        try:
            payload = response.json()
        except ValueError:
            return None, "invalid_json"
        if not isinstance(payload, list):
            return None, "invalid_json"
        raw_all.extend(payload)
        # Follow Link: rel="next" pagination (bounded).
        next_url = None
        link = response.headers.get("Link") or ""
        for part in link.split(","):
            part = part.strip()
            if part.endswith('rel="next"') and part.startswith("<"):
                next_url = part[1:part.index(">")]
                break
        if not next_url:
            break
        url, params = next_url, None
    return raw_all, None


def check_for_update(current_version: str, current_build: int,
                     channel: str = CHANNEL_STABLE, *,
                     force: bool = False) -> UpdateCheckResult:
    """The only network entry point. Never raises for network problems."""
    channel = normalize_channel(channel)
    checked_at = _utc_now()
    try:
        current_build = int(current_build)
    except Exception:
        current_build = 0

    def _result(outcome, latest, error_kind, invalid_tags=0):
        log.info("UPDATE_CHECK channel=%s current=%s+%s outcome=%s "
                 "latest=%s error=%s invalid_tags=%s",
                 channel, current_version, current_build, outcome,
                 latest.tag_name if latest else "-",
                 error_kind or "-", invalid_tags)
        return UpdateCheckResult(outcome, channel, str(current_version),
                                 current_build, latest, error_kind,
                                 checked_at)

    try:
        current_v = _public_version(current_version)
        if current_v is None:
            raise InvalidVersion(str(current_version))
    except InvalidVersion:
        return _result("unknown", None, "local_version_invalid")

    cached = _release_cache.get(channel)
    latest = None
    invalid_tags = 0
    if cached and not force and (time.monotonic() - cached[0]) < _CACHE_TTL_SECONDS:
        latest = cached[1]
    else:
        raw_releases, error_kind = _fetch_releases()
        if error_kind is not None:
            return _result("unknown", None, error_kind)
        parsed = []
        for raw in raw_releases:
            info, invalid = _parse_release(raw, channel)
            if invalid:
                invalid_tags += 1
            if info is not None:
                parsed.append(info)
        if channel == CHANNEL_STABLE:
            candidates = [r for r in parsed if not r.prerelease]
        else:
            candidates = list(parsed)
        latest = _select(candidates)
        if latest is None:
            kind = "no_releases" if parsed or not raw_releases else "no_valid_tags"
            if raw_releases and not parsed:
                kind = "no_valid_tags"
            elif not raw_releases:
                kind = "no_releases"
            return _result("up_to_date", None, kind, invalid_tags)
        _release_cache[channel] = (time.monotonic(), latest)

    latest_v = _public_version(latest.version)
    # Strictly-greater only: the same version (v10.0 vs 10.0, or a
    # packaged 10.0+0) is up-to-date and must never re-offer itself.
    if latest_v is not None and latest_v > current_v:
        return _result("update_available", latest, None, invalid_tags)
    if (latest_v is not None and latest_v == current_v and current_build > 0
            and not latest.prerelease):
        # A dev/beta build of this version moves to its public build.
        return _result("update_available", latest, None, invalid_tags)
    return _result("up_to_date", latest, None, invalid_tags)


def is_update_available(version: str, build: int,
                        channel: str = CHANNEL_STABLE) -> bool:
    """Backward-compatible wrapper (existing callers keep working)."""
    return check_for_update(version, build, channel).outcome == "update_available"


def get_latest_version(channel: str = CHANNEL_STABLE):
    """Backward-compatible wrapper: the selected release's stripped tag,
    or None. Cannot express ``unknown`` — new code must not use it for
    decisions."""
    result = check_for_update(App_Version, App_Build, channel)
    return result.latest.version if result.latest else None
