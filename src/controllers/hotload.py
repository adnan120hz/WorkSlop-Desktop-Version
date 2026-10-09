"""HotLoad: fetch safety rules (dangerous/broken tweaks) from a remote JSON.

The remote JSON lists tweaks that are currently dangerous or broken, scoped to
specific iOS versions / device types. GoldenNugget caches a local copy in the
settings folder, checks for updates on every launch, and warns/blocks the user
from enabling flagged tweaks.

A kill switch in GoldenNugget settings turns the whole system off. When off,
fetches are skipped and no rules are applied.
"""

import json
import logging
import os
import sys
import time
from typing import Optional

import urllib.request

logger = logging.getLogger("WorkSlop.hotload")

from PySide6.QtCore import QStandardPaths

from src.version import App_Version as _APP_VERSION
from src.tweaks.registry import SPECS_BY_SECTION, SECTION_FEATURES

RULES_URL = ("https://raw.githubusercontent.com/adnan120hz/"
             "desk/main/hotload_rules.json")
RULES_FILENAME = "hotload_rules.json"
KILL_SWITCH_KEY = "hotload_enabled"

# A rule with action == KILL_ACTION tells GoldenNugget to fully shut down on
# the matching iOS versions / device types ("remote kill switch").
KILL_ACTION = "kill_app"

# A rule with action == HIDE_ACTION hides a whole feature (page) — its tweaks
# disappear from the UI, its Sidebar button and iOS home card are hidden, and
# presets refuse to load it. Scoped to iOS versions / device types like the
# other rules.
HIDE_ACTION = "hide_feature"

# A rule with action == DISABLE_DAEMON_ACTION force-disables specific daemons
# (field "daemons": a list of Daemon enum names or launchd keys) on matching
# setups: the daemons are always added to the disabled-daemons plist at apply
# time regardless of the UI toggles, their switches are locked ON in the page,
# and presets cannot turn them back on (the apply pass re-forces them).
DISABLE_DAEMON_ACTION = "disable_daemon"

# Feature (page) name -> the tweak names that belong to it. A "hide_feature"
# rule names one of these keys; the UI and the apply/preset paths use this map
# to resolve which tweaks / pages to hide.
#
# Registry-backed features are derived from SPECS_BY_SECTION (a tweak belongs
# to its section's feature automatically). Only the non-registry features and
# a handful of pre-registry members stay explicit here. Sections sharing one
# feature name (LIQUID_GLASS + LIQUID_GLASS_DISABLE both map to
# "Liquid Glass") must MERGE their members: building this with a plain dict
# comprehension silently dropped the whole Liquid Glass v4 set from
# "Liquid Glass" membership (audit round 21/24).
FEATURE_TWEAKS: dict[str, list[str]] = {}
for _section, _feature in SECTION_FEATURES.items():
    _members = [spec.id.name for spec in SPECS_BY_SECTION[_section]]
    FEATURE_TWEAKS.setdefault(_feature, []).extend(
        name for name in _members if name not in FEATURE_TWEAKS.get(_feature, []))
FEATURE_TWEAKS.update({
    # NOTE: "DisableSolarium" and "MetalForceHudEnabled" were listed here as
    # pre-registry members, but no TweakSpec exists for either ID (audit B28)
    # — a hide_feature rule naming them could never match a real tweak.
    # Registry-backed features already cover every real spec via SPECS_BY_SECTION.
    "PosterBoard": ["PosterBoard"],
    "Daemons": ["Daemons", "ClearScreenTimeAgentPlist"],
    "Status Bar": ["StatusBar"],
    "Templates": ["Templates"],
})


def _settings_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not base.endswith("GoldenNugget") and not base.endswith("GoldenNugget/"):
        base = os.path.join(base, "GoldenNugget")
    os.makedirs(base, exist_ok=True)
    return base


def _rules_path() -> str:
    return os.path.join(_settings_dir(), RULES_FILENAME)


def _seed_candidates() -> list:
    """Bundled seed locations for a first run with no cache (Fix Audit 13).

    (a) frozen build: ``hotload_rules.json`` bundled at the PyInstaller
    root (``sys._MEIPASS``, see compile.py); (b) source tree / tests:
    ``hotload_rules.json`` at the repo root, resolved relative to this
    module file (``src/controllers/hotload.py`` -> repo root)."""
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, RULES_FILENAME))
    repo_root = os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    candidates.append(os.path.join(repo_root, RULES_FILENAME))
    return candidates


def _try_load_seed():
    """Load the bundled seed rules, or None.

    Returns ``(parsed, path)`` for the first candidate that exists and
    passes :func:`validate_rules_payload`. A missing or invalid seed
    returns None so the caller stays fail-closed — seeding never
    weakens the corrupt/invalid-cache behaviour."""
    for candidate in _seed_candidates():
        if not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                parsed = json.load(f)
        except Exception as exc:
            logger.warning("HotLoad: bundled seed at %s unreadable (%s) "
                           "— staying fail-closed", candidate, exc)
            return None
        problem = validate_rules_payload(parsed)
        if problem is not None:
            logger.warning("HotLoad: bundled seed at %s invalid (%s) "
                           "— staying fail-closed", candidate, problem)
            return None
        return parsed, candidate
    return None


#: Actions the matching code below actually consumes. A rule whose
#: action is none of these (and which names no tweak) can never match
#: anything, so the schema validator rejects it (Fix Audit 13/84b).
_KNOWN_ACTIONS = (KILL_ACTION, HIDE_ACTION, DISABLE_DAEMON_ACTION)


def validate_rules_payload(parsed) -> Optional[str]:
    """Deep schema check for a HotLoad rules payload (Fix Audit 13/84b).

    ``json.loads`` succeeding used to be the whole validation, so a
    payload like ``{"rules": "yes"}`` or a rule missing every field the
    matcher reads loaded as "valid" and silently matched nothing —
    fail-open with extra steps. Returns ``None`` when the payload is
    usable, or a short description of the first problem. Only the
    fields the matching code really consumes are validated:

    * top level: a dict with ``rules`` as a list (``version``, when
      present, an int);
    * every rule: a dict naming a ``tweak`` (what ``rule_for`` reads)
      and/or a known ``action`` (what ``kill_rule`` / ``hidden_features``
      / ``disabled_daemons`` read); ``hide_feature`` rules must name a
      ``feature``, ``disable_daemon`` rules a ``daemons`` list;
    * the scoping fields, when present, must have the types
      ``_rule_applicable`` compares against (version strings, string
      lists, a bool ``disabled``, a string ``reason``).
    """
    if not isinstance(parsed, dict):
        return "top level is not an object"
    if "rules" not in parsed:
        return "missing 'rules'"
    rules = parsed["rules"]
    if not isinstance(rules, list):
        return "'rules' is not a list"
    version = parsed.get("version")
    if version is not None and (isinstance(version, bool)
                                or not isinstance(version, int)):
        return "'version' is not an integer"
    for idx, rule in enumerate(rules):
        where = f"rule {idx}"
        if not isinstance(rule, dict):
            return f"{where} is not an object"
        tweak = rule.get("tweak")
        action = rule.get("action")
        if tweak is not None and (not isinstance(tweak, str) or not tweak):
            return f"{where}: 'tweak' is not a non-empty string"
        if action is not None and action not in _KNOWN_ACTIONS:
            return f"{where}: unknown action {action!r}"
        if tweak is None and action is None:
            return f"{where} names neither a tweak nor an action"
        if action == HIDE_ACTION:
            feature = rule.get("feature")
            if not isinstance(feature, str) or not feature:
                return f"{where}: hide_feature rule names no feature"
        if action == DISABLE_DAEMON_ACTION:
            daemons = rule.get("daemons")
            if (not isinstance(daemons, list)
                    or not all(isinstance(d, str) for d in daemons)):
                return f"{where}: disable_daemon rule has no daemon list"
        for key in ("min_version", "max_version",
                    "min_app_version", "max_app_version", "reason"):
            if key in rule and not isinstance(rule[key], str):
                return f"{where}: '{key}' is not a string"
        for key in ("app_versions", "only_models"):
            if key in rule and (not isinstance(rule[key], list)
                                or not all(isinstance(v, str)
                                           for v in rule[key])):
                return f"{where}: '{key}' is not a list of strings"
        if "disabled" in rule and not isinstance(rule["disabled"], bool):
            return f"{where}: 'disabled' is not a boolean"
    return None


def _unavailable_reason(hotload) -> Optional[str]:
    """Why the cached rules cannot be trusted, or None when they can.

    Bare instances (tests building ``HotLoad`` via ``object.__new__``
    and assigning ``_rules`` by hand) carry no load state and count as
    available; only a real load that failed marks the cache unusable.
    """
    if getattr(hotload, "_rules_available", None) is False:
        return getattr(hotload, "_rules_error", None) or "cache unreadable"
    return None


class HotLoad:
    def __init__(self, settings=None):
        self.settings = settings
        self._rules = {"version": 0, "rules": []}
        # Fix Audit 13/84b: whether the cache actually yielded a valid
        # rules payload. The gates below fail CLOSED while this is
        # False (see _load_local), instead of the old behaviour where a
        # missing/corrupt cache silently meant "no rules, all allowed".
        self._rules_available = False
        self._rules_error: Optional[str] = None
        self._load_local()

    # --- storage ---------------------------------------------------------
    def _load_local(self):
        path = _rules_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                parsed = json.load(f)
        except FileNotFoundError:
            # Fix Audit 13 (seeding): a first run has no cache yet, and
            # failing closed there hides/refuses every gated feature
            # before the first fetch can succeed (also offline). Fall
            # back to the bundled seed rules; only when no valid seed
            # exists does the missing cache stay fail-closed.
            seeded = _try_load_seed()
            if seeded is not None:
                parsed, seed_path = seeded
                self._rules = parsed
                self._rules_available = True
                self._rules_error = None
                logger.info("HotLoad: no cached rules file at %s — "
                            "using bundled seed rules from %s",
                            path, seed_path)
                return
            self._rules = {"version": 0, "rules": []}
            self._rules_available = False
            self._rules_error = f"no cached rules file at {path}"
            logger.warning("HotLoad: %s — gated features fail closed "
                           "until rules are fetched", self._rules_error)
            return
        except Exception as exc:  # unreadable / not JSON at all
            self._rules = {"version": 0, "rules": []}
            self._rules_available = False
            self._rules_error = f"cached rules unreadable: {exc}"
            logger.warning("HotLoad: %s — gated features fail closed",
                           self._rules_error)
            return
        problem = validate_rules_payload(parsed)
        if problem is not None:
            self._rules = {"version": 0, "rules": []}
            self._rules_available = False
            self._rules_error = f"cached rules invalid: {problem}"
            logger.warning("HotLoad: %s — gated features fail closed",
                           self._rules_error)
            return
        self._rules = parsed
        self._rules_available = True
        self._rules_error = None

    def is_enabled(self) -> bool:
        if self.settings is None:
            return True
        try:
            return bool(self.settings.value(KILL_SWITCH_KEY, True, type=bool))
        except Exception:
            return True

    def set_enabled(self, enabled: bool):
        if self.settings is None:
            return
        self.settings.setValue(KILL_SWITCH_KEY, bool(enabled))
        try:
            self.settings.sync()
        except Exception:
            # Fix Audit 13/84b: was a bare ``except: pass`` — a kill
            # switch that failed to persist looked exactly like one
            # that saved. Behaviour unchanged (never raise), but the
            # failure is now on the record.
            logger.warning("HotLoad: persisting the kill switch "
                           "failed", exc_info=True)

    # --- fetching --------------------------------------------------------
    def update(self, url: Optional[str] = None) -> bool:
        """Fetch fresh rules and cache them in the settings folder. On any
        failure the existing local copy is kept (rules always load locally).

        Returns True when a rule set was fetched successfully, False otherwise.
        """
        if not self.is_enabled():
            return False
        url = url or RULES_URL
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "WorkSlopDesktop"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            parsed = json.loads(data.decode("utf-8"))
            problem = validate_rules_payload(parsed)
            if problem is not None:
                # Fix Audit 13/84b: a fetched payload that only parses
                # as JSON is not a rules file — keep the old cache and
                # say why, instead of caching a fail-open shell.
                logger.warning("HotLoad: fetched rules invalid (%s) — "
                               "keeping the previous cache", problem)
                return False
            parsed["_fetched_at"] = int(time.time())
            path = _rules_path()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(parsed, f, ensure_ascii=False, indent=2)
            self._rules = parsed
            self._rules_available = True
            self._rules_error = None
            return True
        except Exception as e:
            logger.error("[HotLoad] update failed: %s", e)
            return False

    # --- matching --------------------------------------------------------
    def rule_for(self, tweak_id, device_version=None, device_model=None,
                 app_version=None) -> Optional[dict]:
        """Return the first applicable rule for a tweak (by its TweakID name),
        or None when it is not flagged for this device/iOS/app. The kill switch
        being off returns None for everything."""
        if not self.is_enabled():
            return None
        tweak_name = getattr(tweak_id, "name", str(tweak_id))
        unavailable = _unavailable_reason(self)
        if unavailable is not None:
            # Fix Audit 13/84b: fail CLOSED. With no trustworthy rules
            # the gate cannot know this tweak is safe, so it refuses
            # (callers skip/block on any returned rule) instead of the
            # old fail-open "no rules cached = everything allowed".
            return {
                "tweak": tweak_name,
                "action": "hotload_unavailable",
                "reason": ("HotLoad safety rules are unavailable "
                           f"({unavailable}); gated features refuse "
                           "to run until the rules load."),
            }
        for rule in self._rules.get("rules", []):
            try:
                if rule.get("tweak") != tweak_name:
                    continue
                if not self._rule_applicable(rule, device_version, device_model, app_version):
                    continue
                return rule
            except Exception:
                continue
        return None

    def kill_rule(self, device_version=None, device_model=None,
                  app_version=None) -> Optional[dict]:
        """Return the first applicable rule that fully disables GoldenNugget
        on this device/iOS/app (action == "kill_app"), or None.

        This is the remote "kill switch": a matching rule means the app should
        not initialize (or, if already running, should shut down like a crash).
        """
        if not self.is_enabled():
            return None
        unavailable = _unavailable_reason(self)
        if unavailable is not None:
            # Fix Audit 13/84b: fail CLOSED at the app-level gate too —
            # no trustworthy rules means the kill-switch check itself
            # cannot pass, so it reports as killed with the reason.
            return {
                "action": KILL_ACTION,
                "reason": ("HotLoad safety rules are unavailable "
                           f"({unavailable}); refusing to run until "
                           "the rules load."),
            }
        for rule in self._rules.get("rules", []):
            try:
                if rule.get("action") != KILL_ACTION:
                    continue
                if not self._rule_applicable(rule, device_version, device_model, app_version):
                    continue
                return rule
            except Exception:
                continue
        return None

    def feature_for(self, tweak_id) -> Optional[str]:
        """Return the feature (page) name a tweak belongs to, or None."""
        name = getattr(tweak_id, "name", str(tweak_id))
        for feature, members in FEATURE_TWEAKS.items():
            if name in members:
                return feature
        return None

    def hidden_features(self, device_version=None, device_model=None,
                        app_version=None) -> set:
        """Set of feature (page) names hidden by "hide_feature" rules for this
        setup. These features are removed from the UI entirely and their tweaks
        never apply — the whole point is to keep broken/dangerous features out
        of sight so nobody can enable them accidentally."""
        if not self.is_enabled():
            return set()
        if _unavailable_reason(self) is not None:
            # Fix Audit 13/84b: fail CLOSED — with no trustworthy rules
            # every gated feature is treated as hidden (refuses to run)
            # rather than silently shown and runnable.
            return set(FEATURE_TWEAKS)
        hidden = set()
        for rule in self._rules.get("rules", []):
            try:
                if rule.get("action") != HIDE_ACTION:
                    continue
                if not self._rule_applicable(rule, device_version, device_model, app_version):
                    continue
                feature = rule.get("feature")
                if feature and feature in FEATURE_TWEAKS:
                    hidden.add(feature)
            except Exception:
                continue
        return hidden

    def hidden_tweak_names(self, device_version=None, device_model=None,
                           app_version=None) -> set:
        """Set of every tweak name that belongs to a currently-hidden feature."""
        names = set()
        hidden = self.hidden_features(device_version, device_model, app_version)
        for feature in hidden:
            names.update(FEATURE_TWEAKS[feature])
        return names

    def disabled_daemons(self, device_version=None, device_model=None,
                         app_version=None) -> dict:
        """Daemons force-disabled by "disable_daemon" rules for this setup,
        as {daemon name-or-key: reason}. Empty when the kill switch is off or
        no rule matches. The first matching rule per daemon wins."""
        if not self.is_enabled():
            return {}
        forced = {}
        for rule in self._rules.get("rules", []):
            try:
                if rule.get("action") != DISABLE_DAEMON_ACTION:
                    continue
                if not self._rule_applicable(rule, device_version, device_model, app_version):
                    continue
                reason = rule.get("reason")
                for item in rule.get("daemons") or []:
                    name = str(item).strip()
                    if not name:
                        continue
                    forced.setdefault(name, reason)
            except Exception:
                continue
        return forced

    def disabled_daemon_keys(self, device_version=None, device_model=None,
                             app_version=None) -> set:
        """Resolve "disable_daemon" rules into the concrete launchd keys that
        must sit in the disabled-daemons plist on this setup. Accepts either
        Daemon enum member names (e.g. "ScreenTime") or raw launchd keys."""
        names = self.disabled_daemons(device_version, device_model, app_version)
        if not names:
            return set()
        from src.tweaks.daemons_tweak import Daemon
        members = {d.name: d for d in Daemon}
        all_keys = {k for d in Daemon for k in d.value}
        keys = set()
        for name in names:
            member = members.get(name)
            if member is not None:
                keys.update(member.value)
            elif name in all_keys:
                keys.add(name)
        return keys

    # --- helpers ---------------------------------------------------------
    @staticmethod
    def _compare(v1, v2):
        a = [int(x) for x in str(v1).replace(",", ".").split(".") if x.isdigit()]
        b = [int(x) for x in str(v2).replace(",", ".").split(".") if x.isdigit()]
        a += [0] * (len(b) - len(a))
        b += [0] * (len(a) - len(b))
        return (a > b) - (a < b)

    def _rule_applicable(self, rule: dict, device_version, device_model,
                         app_version: Optional[str] = None) -> bool:
        """Whether a rule applies to this setup: it is enabled and its version
        (app and/or iOS) / model bounds match. When no app_version is given,
        the running app's own version is used (so existing callers are scoped
        automatically)."""
        if rule.get("disabled", True) is False:
            return False
        if app_version is None:
            app_version = _APP_VERSION
        return (self._app_version_applicable(rule, app_version)
                and self._version_applicable(rule, device_version)
                and self._model_applicable(rule, device_model))

    def _app_version_applicable(self, rule: dict, app_version) -> bool:
        """App-version scoping of a rule (the version the rule "propagates"
        to): exact set via ``app_versions`` or a range via
        ``min_app_version`` / ``max_app_version``."""
        exact = rule.get("app_versions")
        if exact:
            if app_version is None:
                return False
            return any(self._compare(app_version, v) == 0 for v in exact)
        lo = rule.get("min_app_version")
        hi = rule.get("max_app_version")
        if lo is None and hi is None:
            return True
        if app_version is None:
            return False
        v = str(app_version)
        if lo is not None and self._compare(v, str(lo)) < 0:
            return False
        if hi is not None and self._compare(v, str(hi)) > 0:
            return False
        return True

    def _version_applicable(self, rule: dict, device_version) -> bool:
        lo = rule.get("min_version")
        hi = rule.get("max_version")
        if lo is None and hi is None:
            return True
        if device_version is None:
            return False
        v = str(device_version)
        if lo is not None and self._compare(v, str(lo)) < 0:
            return False
        if hi is not None and self._compare(v, str(hi)) > 0:
            return False
        return True

    def _model_applicable(self, rule: dict, device_model) -> bool:
        only = rule.get("only_models")
        if not only:
            return True
        if device_model is None:
            return False
        model = str(device_model)
        return any(model.startswith(p) for p in only)


def confirm_flagged(rule: dict, parent=None) -> bool:
    """Show the warning for a flagged tweak. Returns True (Continue Anyway)
    to allow, or False (Cancel) to block."""
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QMessageBox

    tweak = rule.get("tweak", "this tweak")
    reason = rule.get("reason")
    if reason:
        reason_txt = str(reason)
    else:
        reason_txt = QCoreApplication.translate(
            "Nugget",
            "This feature is currently flagged as dangerous or broken.")
    # REAUDIT FIX: warning text said "GoldenNugget" — user-visible dialog.
    # (Audit round 25: the dialog now goes through tr() with static literals;
    # the tweak name is inserted with %1, never an f-string.)
    text = QCoreApplication.translate(
        "Nugget",
        "WorkSlop Desktop safety rules have flagged “%1” as currently "
        "dangerous or broken.\n\n%2\n\n"
        "It is recommended not to enable it. Do you still want to enable it?"
    ).arg(str(tweak), reason_txt)
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(QCoreApplication.translate(
        "Nugget", "Disabled Feature Warning"))
    box.setText(text)
    continue_btn = box.addButton(
        QCoreApplication.translate("Nugget", "Continue Anyway"),
        QMessageBox.ButtonRole.AcceptRole)
    cancel_btn = box.addButton(
        QCoreApplication.translate("Nugget", "Cancel"),
        QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel_btn)
    box.exec()
    return box.clickedButton() is continue_btn
