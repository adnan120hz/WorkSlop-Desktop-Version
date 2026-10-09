#!/usr/bin/env python3
"""Fix Audit 13 + 84b: HotLoad failed open on an empty/broken cache.

(a) A missing, unreadable or schema-invalid cache used to load as
    ``{"version": 0, "rules": []}`` — indistinguishable from "no tweak
    is dangerous" — so every gated feature ran. The gates now fail
    CLOSED: ``rule_for`` returns a refusal rule, ``kill_rule`` reports
    the app-level gate as tripped, and ``hidden_features`` hides every
    gated feature, each carrying the reason. A VALID cache with an
    empty rules list still means "nothing flagged" and gates pass.
(b) Validation is deeper than ``json.loads``: the payload and every
    rule are checked against the fields the matcher really consumes.
(c) The kill-switch persist ``except: pass`` now logs; behaviour
    (never raise) is unchanged. The user's explicit kill-switch OFF
    still turns the system off — that is a choice, not a failure.
(d) Seeding (wave 2): a missing cache first tries the bundled seed
    rules (``sys._MEIPASS`` / repo-root ``hotload_rules.json``,
    validated like any payload, bundled by compile.py). A valid seed
    makes the first run usable; no seed or an invalid seed keeps the
    fail-closed behaviour in (a), and a corrupt/invalid CACHE never
    falls back to the seed.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python \
    tools/test_audit13_84b_hotload_failclosed.py
"""
import json
import logging
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="workslop-a13-")
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="workslop-a13-")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


import src.controllers.hotload as hotload_mod  # noqa: E402
from src.controllers.hotload import (  # noqa: E402
    FEATURE_TWEAKS, HotLoad, validate_rules_payload)

TMP = tempfile.mkdtemp(prefix="workslop-a13-cache-")
CACHE = os.path.join(TMP, "hotload_rules.json")
hotload_mod._rules_path = lambda: CACHE


def write_cache(payload):
    if payload is None:
        try:
            os.remove(CACHE)
        except OSError:
            pass
    elif isinstance(payload, bytes):
        with open(CACHE, "wb") as f:
            f.write(payload)
    else:
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(payload, f)


def gates_refuse(hl, label):
    rule = hl.rule_for("AnythingAtAll")
    check(f"{label}: rule_for refuses (fail-closed)",
          rule is not None and rule.get("action") == "hotload_unavailable",
          repr(rule))
    check(f"{label}: refusal carries the reason",
          bool(rule and "unavailable" in str(rule.get("reason", ""))),
          repr(rule))
    kill = hl.kill_rule("26.6.1", "iPhone14,5")
    check(f"{label}: kill gate tripped (fail-closed)",
          kill is not None and "unavailable" in str(kill.get("reason", "")),
          repr(kill))
    check(f"{label}: every gated feature hidden",
          hl.hidden_features("26.6.1", "iPhone14,5") == set(FEATURE_TWEAKS))
    check(f"{label}: hidden tweak names non-empty",
          len(hl.hidden_tweak_names("26.6.1", "iPhone14,5")) > 0)


# Fix Audit 13 (seeding): with NO valid seed a missing cache still
# fails closed (assertions unchanged); with a valid bundled seed the
# first run loads it instead. The no-seed case is simulated by pointing
# the seed candidates at nothing.
_REAL_SEED_CANDIDATES = hotload_mod._seed_candidates
hotload_mod._seed_candidates = lambda: []

print("\n(a) missing cache fails closed")
write_cache(None)
gates_refuse(HotLoad(None), "missing cache")

print("\n(a-seed) missing cache loads a valid bundled seed")
SEED = os.path.join(TMP, "seed_rules.json")
with open(SEED, "w", encoding="utf-8") as f:
    json.dump({"version": 9, "rules": [
        {"tweak": "SeededBad", "reason": "seeded", "disabled": True}]}, f)
hotload_mod._seed_candidates = lambda: [SEED]
seed_records = []


class _SeedCapture(logging.Handler):
    def emit(self, record):
        seed_records.append(record.getMessage())


_seed_logger = logging.getLogger("WorkSlop.hotload")
_seed_logger.addHandler(_SeedCapture())
_seed_logger.setLevel(logging.INFO)
try:
    hl = HotLoad(None)
finally:
    _seed_logger.removeHandler(_SeedCapture())
check("seeded rules are available (not fail-closed)",
      hl.rule_for("AnythingAtAll") is None, repr(hl.rule_for("AnythingAtAll")))
check("seeded rule matches",
      (hl.rule_for("SeededBad") or {}).get("reason") == "seeded")
check("seeded: no kill tripped", hl.kill_rule() is None)
check("seeded: nothing hidden without a hide rule",
      hl.hidden_features() == set())
check("seed use is logged honestly",
      any("bundled seed" in m for m in seed_records), repr(seed_records))

print("\n(a-seed2) an invalid seed stays fail-closed")
BAD_SEED = os.path.join(TMP, "bad_seed.json")
with open(BAD_SEED, "w", encoding="utf-8") as f:
    f.write("{not json")
hotload_mod._seed_candidates = lambda: [BAD_SEED]
gates_refuse(HotLoad(None), "invalid seed")
hotload_mod._seed_candidates = lambda: []

print("\n(a-seed3) compile.py bundles the seed for frozen builds")
compile_src = open(os.path.join(os.path.dirname(__file__), "..",
                                "compile.py"), encoding="utf-8").read()
check("compile.py adds hotload_rules.json as bundle data",
      "--add-data=hotload_rules.json" in compile_src)

print("\n(a2) corrupt cache fails closed")
write_cache(b"{this is not json")
gates_refuse(HotLoad(None), "corrupt cache")

print("\n(a3) schema-invalid cache fails closed (was: silently valid)")
write_cache({"rules": "yes"})
gates_refuse(HotLoad(None), "schema-invalid cache")

print("\n(b) the schema validator checks what the matcher consumes")
check("valid empty payload passes",
      validate_rules_payload({"version": 1, "rules": []}) is None)
check("tweak-only rule passes (the live cache shape)",
      validate_rules_payload({"rules": [{"tweak": "Daemons",
                                         "disabled": True}]}) is None)
check("kill_app rule passes",
      validate_rules_payload({"rules": [{"action": "kill_app",
                                         "disabled": False}]}) is None)
check("disable_daemon rule with daemon list passes",
      validate_rules_payload({"rules": [{"action": "disable_daemon",
                                         "daemons": ["ScreenTime"]}]}) is None)
for payload, needle in (
        ({"rules": "yes"}, "not a list"),
        ({"version": "one", "rules": []}, "version"),
        ({"rules": [{}]}, "neither a tweak nor an action"),
        ({"rules": [{"action": "explode"}]}, "unknown action"),
        ({"rules": [{"action": "hide_feature"}]}, "no feature"),
        ({"rules": [{"action": "disable_daemon", "daemons": "all"}]},
         "daemon list"),
        ({"rules": [{"tweak": "X", "min_version": 26}]}, "not a string"),
        ({"rules": [{"tweak": "X", "only_models": "iPhone"}]},
         "list of strings"),
        ({"rules": [{"tweak": "X", "disabled": "yes"}]}, "boolean")):
    problem = validate_rules_payload(payload)
    check(f"rejects {needle}: {payload!r}"[:80],
          problem is not None and needle in problem, repr(problem))

print("\n(a4) a VALID cache — even with zero rules — gates normally")
write_cache({"version": 1, "rules": []})
hl = HotLoad(None)
check("empty-but-valid rules: rule_for passes", hl.rule_for("X") is None)
check("empty-but-valid rules: no kill", hl.kill_rule() is None)
check("empty-but-valid rules: nothing hidden", hl.hidden_features() == set())

write_cache({"version": 1, "rules": [
    {"tweak": "BadTweak", "reason": "broken", "disabled": True}]})
hl = HotLoad(None)
check("matching rule still returned",
      (hl.rule_for("BadTweak") or {}).get("reason") == "broken")
check("non-matching tweak still passes", hl.rule_for("GoodTweak") is None)

print("\n(c) kill-switch persist failure is logged, never raised")
records = []


class _Capture(logging.Handler):
    def emit(self, record):
        records.append(record.getMessage())


hotload_logger = logging.getLogger("WorkSlop.hotload")
hotload_logger.addHandler(_Capture())
hotload_logger.setLevel(logging.WARNING)


class _BadSettings:
    def setValue(self, key, val):
        pass

    def sync(self):
        raise OSError("disk full")

    def value(self, key, default=None, type=None):  # noqa: A002
        return True


hl = HotLoad(_BadSettings())
hl.set_enabled(False)  # must not raise
check("persist failure logged",
      any("persisting the kill switch" in m for m in records),
      repr(records))

print("\n(d) explicit kill-switch OFF still turns the system off")
write_cache(None)


class _OffSettings:
    def value(self, key, default=None, type=None):  # noqa: A002
        return False

    def setValue(self, key, val):
        pass

    def sync(self):
        pass


hl = HotLoad(_OffSettings())
check("off: rule_for passes despite missing cache", hl.rule_for("X") is None)
check("off: no kill despite missing cache", hl.kill_rule() is None)
check("off: nothing hidden despite missing cache",
      hl.hidden_features() == set())

print(f"\nALL {PASS} CHECKS PASSED")
