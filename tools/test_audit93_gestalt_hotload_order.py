#!/usr/bin/env python3
"""Fix Audit 93: HotLoad gate for the standalone Gestalt apply +
deterministic apply order with explicit duplicate-key logging.

(a) ``_apply_gestalt_tweaks`` (MobileGestalt page apply) used to bypass
    HotLoad completely. It now passes the same gate as the main apply:
    the app-level ``kill_app`` rule refuses the whole apply, and the
    per-tweak hidden-feature / ``rule_for`` gate skips flagged tweaks
    (refusing honestly when every enabled tweak is flagged).
(b) Apply staging follows registry (``SPECS``) order, not the
    navigation-dependent ``tweaks``-dict insertion order; two different
    loader histories stage byte-identical plist payloads.
(c) Duplicate shared-plist keys (two enabled tweaks writing the same
    key into the same location) are logged explicitly with key,
    location and the colliding tweaks.

Offline: HotLoad / lockdown / restore are faked, no device is touched.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python \
    tools/test_audit93_gestalt_hotload_order.py
"""
import asyncio
import logging
import os
import plistlib
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TMP = tempfile.mkdtemp(prefix="works93-")
os.environ["WORKSLOP_APPLY_JOURNAL_DIR"] = os.path.join(TMP, "journal")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

import src.devicemanagement.device_manager as dm_mod  # noqa: E402
from src.devicemanagement.device_manager import (  # noqa: E402
    deterministic_tweak_items, find_plist_key_conflicts,
    log_plist_key_conflicts)
from src.exceptions.nugget_exception import NuggetException  # noqa: E402
from src.tweaks.registry import SPECS  # noqa: E402
from src.tweaks.tweak_names import TweakID  # noqa: E402
from src.tweaks.tweaks import tweaks  # noqa: E402


# ---------------------------------------------------------------- (a)
class FakeHotLoad:
    """Same surface the main apply gate uses, scripted per case."""

    kill = None
    flagged = set()
    hidden = set()

    def __init__(self, settings=None):
        pass

    def kill_rule(self, version=None, model=None):
        return FakeHotLoad.kill

    def hidden_tweak_names(self, device_version=None, device_model=None):
        return set(FakeHotLoad.hidden)

    def rule_for(self, tid, device_version=None, device_model=None):
        name = tid.name if hasattr(tid, "name") else str(tid)
        if name in FakeHotLoad.flagged:
            return {"tweak": name, "reason": "flagged in test"}
        return None


def make_gestalt_dm(captured):
    from contextlib import asynccontextmanager
    from src.tweaks.tweak_loader import load_mobilegestalt
    load_mobilegestalt(build="23C5027f", version="26.1")
    dm = dm_mod.DeviceManager()
    dm.get_current_device_name = lambda: "Test iPhone"
    dm.get_current_device_model = lambda: "iPhone14,5"
    dm.get_current_device_version = lambda: "26.1"
    dm.get_current_device_build = lambda: "23C5027f"
    dm.get_current_device_udid = lambda: "TESTUDID-93"
    dm.data_singleton.current_device = SimpleNamespace(
        connected_via_usb=True, version="26.1", build="23C5027f")
    dm._load_gestalt_plist = lambda update_label=None: {
        "CacheExtra": {"oPeik/9e8lQWMszEjbPzng": {}}}
    dm.pref_manager.auto_reboot = False

    @asynccontextmanager
    async def fake_lockdown(serial=None, **kw):
        yield SimpleNamespace()

    async def fake_restore_files(**kw):
        captured["restore_called"] = True
        captured["files"] = list(kw.get("files") or [])
        return "OK"

    dm_mod.lockdown_session = fake_lockdown
    dm_mod.restore_files = fake_restore_files
    return dm


def test_gestalt_hotload_gate():
    print("\n(a) standalone Gestalt apply passes the main HotLoad gate")
    real_hotload = dm_mod.HotLoad
    real_lockdown, real_restore = dm_mod.lockdown_session, dm_mod.restore_files
    dm_mod.HotLoad = FakeHotLoad
    from src.tweaks.tweak_loader import load_mobilegestalt
    load_mobilegestalt(build="23C5027f", version="26.1")
    model_name = tweaks[TweakID.ModelName]
    model_name.set_value("iPhone 99", toggle_enabled=False)
    model_name.set_enabled(True)
    try:
        # kill_app rule -> whole apply refused, nothing restored.
        captured = {"restore_called": False}
        dm = make_gestalt_dm(captured)
        FakeHotLoad.kill = {"reason": "iOS blocked in test"}
        FakeHotLoad.flagged, FakeHotLoad.hidden = set(), set()
        try:
            dm.apply_gestalt_tweaks(lambda x: None, lambda x: None)
            raised = None
        except NuggetException as e:
            raised = str(e)
        check("kill_app rule refuses the gestalt apply",
              raised is not None and "HotLoad" in raised, repr(raised))
        check("kill_app refusal restores nothing",
              not captured["restore_called"])

        # Per-tweak rule on the only enabled tweak -> honest refusal.
        FakeHotLoad.kill = None
        FakeHotLoad.flagged = {"ModelName"}
        captured = {"restore_called": False}
        dm = make_gestalt_dm(captured)
        try:
            dm.apply_gestalt_tweaks(lambda x: None, lambda x: None)
            raised = None
        except NuggetException as e:
            raised = str(e)
        check("flagged-only gestalt apply refused honestly",
              raised is not None and "HotLoad" in raised, repr(raised))
        check("flagged refusal restores nothing",
              not captured["restore_called"])

        # Hidden-feature membership blocks the same way.
        FakeHotLoad.flagged = set()
        FakeHotLoad.hidden = {"ModelName"}
        captured = {"restore_called": False}
        dm = make_gestalt_dm(captured)
        try:
            dm.apply_gestalt_tweaks(lambda x: None, lambda x: None)
            raised = None
        except NuggetException as e:
            raised = str(e)
        check("hidden-feature gestalt tweak blocked",
              raised is not None and "HotLoad" in raised, repr(raised))

        # No gate hit -> the apply runs (same fake restore as before).
        FakeHotLoad.hidden = set()
        captured = {"restore_called": False}
        dm = make_gestalt_dm(captured)
        alert = None
        try:
            asyncio.run(dm._apply_gestalt_tweaks(lambda x: None,
                                                 lambda x: None))
            alert = True
        except Exception as e:  # noqa: BLE001
            alert = f"{type(e).__name__}: {e}"
        check("ungated gestalt apply still restores",
              captured["restore_called"], repr(alert))
    finally:
        model_name.set_enabled(False)
        FakeHotLoad.kill, FakeHotLoad.flagged = None, set()
        FakeHotLoad.hidden = set()
        dm_mod.HotLoad = real_hotload
        dm_mod.lockdown_session, dm_mod.restore_files = (
            real_lockdown, real_restore)


# ---------------------------------------------------------------- (b)
def simulate_history(order):
    """Rebuild the global tweaks dict via one loader-call history."""
    from src.devicemanagement.constants import mobilegestalt_decision
    from src.tweaks import tweak_loader as tl
    from src.tweaks.eligibility_tweak import BookRestoreFileTweak
    from src.tweaks.icon_themes.icon_themes_tweak import IconThemesTweak
    from src.tweaks.nugget_lg import load_nugget_lg_tweaks
    from src.tweaks.posterboard.posterboard_tweak import PosterboardTweak
    from src.tweaks.posterboard.template_options.templates_tweak import (
        TemplatesTweak)
    from src.tweaks.status_bar.status_bar_tweak import StatusBarTweak
    dec = mobilegestalt_decision("23A341", "18.0")
    tweaks.clear()
    tweaks.update({
        TweakID.PosterBoard: PosterboardTweak(),
        TweakID.Templates: TemplatesTweak(),
        TweakID.StatusBar: StatusBarTweak(),
        TweakID.IconThemes: IconThemesTweak(),
        TweakID.CreateBRFolders: BookRestoreFileTweak(),
    })
    steps = {
        "plist": tl.load_plist_tweaks,
        "daemons": tl.load_daemons,
        "risky": tl.load_risky,
        "mobile": lambda: tl.load_mobilegestalt(decision=dec),
        "elig": lambda: tl.load_eligibility(None, dec),
        "rdar": lambda: tl.load_rdar_fix(None, dec),
        "nugget": load_nugget_lg_tweaks,
    }
    for name in order:
        steps[name]()
    return deterministic_tweak_items(), list(tweaks)


def stage_payload(items):
    """Stage Basic/Advanced/FeatureFlag writes exactly as the pass does."""
    from src.tweaks.tweak_classes import (
        AdvancedPlistTweak, BasicPlistTweak, FeatureFlagTweak)
    basic, flags = {}, {}
    for _tid, tw in items:
        if not getattr(tw, "enabled", False):
            continue
        if isinstance(tw, FeatureFlagTweak):
            flags = tw.apply_tweak(flags)
        elif isinstance(tw, (BasicPlistTweak, AdvancedPlistTweak)):
            basic = tw.apply_tweak(basic)
    staged = {loc.value: plistlib.dumps(d, fmt=plistlib.FMT_BINARY,
                                         sort_keys=True)
              for loc, d in basic.items()}
    if flags:
        staged["FeatureFlags"] = plistlib.dumps(
            flags, fmt=plistlib.FMT_BINARY, sort_keys=True)
    return staged


def enable_all_plist_tweaks():
    from src.tweaks.tweak_classes import (
        AdvancedPlistTweak, BasicPlistTweak, FeatureFlagTweak)
    enabled = []
    for tid, tw in tweaks.items():
        if isinstance(tw, (BasicPlistTweak, AdvancedPlistTweak,
                           FeatureFlagTweak)):
            tw.set_enabled(True)
            enabled.append(tid)
    return enabled


def test_deterministic_order():
    print("\n(b) deterministic registry order, navigation-independent")
    hist_a = ["plist", "daemons", "mobile", "elig", "risky", "rdar",
              "nugget"]
    hist_b = ["nugget", "rdar", "risky", "elig", "mobile", "daemons",
              "plist"]
    items_a, raw_a = simulate_history(hist_a)
    enabled = enable_all_plist_tweaks()
    payload_a = stage_payload(items_a)
    for tid in enabled:
        tweaks[tid].set_enabled(False)
    items_b, raw_b = simulate_history(hist_b)
    enabled = enable_all_plist_tweaks()
    payload_b = stage_payload(items_b)
    for tid in enabled:
        tweaks[tid].set_enabled(False)

    spec_order = [s.id for s in SPECS if not s.disabled]
    reg_a = [tid for tid, _ in items_a if tid in spec_order]
    reg_b = [tid for tid, _ in items_b if tid in spec_order]
    check("raw dict orders really differ across histories",
          raw_a != raw_b, f"{len(raw_a)} vs {len(raw_b)} tweaks")
    check("registry subsequence follows SPECS order (history A)",
          reg_a == [s for s in spec_order if s in dict(items_a)],
          f"{len(reg_a)} registry tweaks")
    check("registry subsequence identical across histories",
          reg_a == reg_b)
    check("staged payload bytes identical across histories",
          payload_a == payload_b,
          f"{len(payload_a)} files, "
          f"A-only={sorted(set(payload_a) ^ set(payload_b))}")
    # The v4 Liquid Glass GP payload is part of that staged set.
    gp = [k for k in payload_a if k.endswith(".GlobalPreferences.plist")
          and "Managed Preferences" in k]
    check("Liquid Glass v4 GP file staged in both histories", bool(gp),
          repr(gp))


# ---------------------------------------------------------------- (c)
class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def test_conflict_logging():
    print("\n(c) duplicate plist keys are logged explicitly")
    from src.tweaks.tweak_loader import load_plist_tweaks
    from src.tweaks.nugget_lg import load_nugget_lg_tweaks
    load_plist_tweaks()
    load_nugget_lg_tweaks()
    logger = logging.getLogger("GoldenNugget.protective")
    handler = ListHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    touched = []
    try:
        # Registry v4 vs Nugget twin: same GP key SBDisallowGlassTime.
        for tid in (TweakID.DisallowGlassTime, TweakID.NuggetNoLiquidClock):
            tweaks[tid].set_enabled(True)
            touched.append(tid)
        items = deterministic_tweak_items()
        conflicts = find_plist_key_conflicts(items)
        hit = [c for c in conflicts if c["key"] == "SBDisallowGlassTime"]
        check("v4/Nugget GP duplicate detected",
              bool(hit) and set(hit[0]["tweaks"]) ==
              {"DisallowGlassTime", "NuggetNoLiquidClock"}, repr(hit))
        check("conflict names the GP location",
              bool(hit) and hit[0]["location"].endswith(
                  ".GlobalPreferences.plist"), repr(hit))
        handler.messages.clear()
        log_plist_key_conflicts(items)
        logged = "\n".join(handler.messages)
        check("conflict logged with key + location + tweaks",
              "SBDisallowGlassTime" in logged
              and ".GlobalPreferences.plist" in logged
              and "DisallowGlassTime" in logged
              and "NuggetNoLiquidClock" in logged, logged[:300])

        # Gestalt CacheExtra duplicate: Enable/Disable LGLPM pair.
        from src.tweaks.tweak_loader import load_mobilegestalt
        load_mobilegestalt(build="23C5027f", version="26.1")
        for tid in (TweakID.EnableLGLPM, TweakID.DisableLGLPM):
            tweaks[tid].enabled = True  # bypass mutual exclusion on purpose
            touched.append(tid)
        gconf = find_plist_key_conflicts(
            deterministic_tweak_items(), gestalt=True)
        ghit = [c for c in gconf
                if c["key"] == "SAGvsp6O6kAQ4fEfDJpC4Q"]
        check("LGLPM CacheExtra duplicate detected",
              bool(ghit) and set(ghit[0]["tweaks"]) ==
              {"EnableLGLPM", "DisableLGLPM"}, repr(ghit))
    finally:
        for tid in touched:
            try:
                tweaks[tid].set_enabled(False)
            except Exception:
                tweaks[tid].enabled = False
        logger.removeHandler(handler)


test_gestalt_hotload_gate()
test_deterministic_order()
test_conflict_logging()
print(f"\nALL {PASS} CHECKS PASSED")
