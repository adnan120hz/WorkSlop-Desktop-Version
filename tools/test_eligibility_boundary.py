"""Targeted proof for the Eligibility build boundary (user order 2026-10-03).

Bug: the Eligibility tweaks (EUEnabler / AIEligibility / CreateBRFolders,
via ``tweak_loader.load_eligibility()``) stayed activatable on iOS 26.6.1
RC even though Eligibility is blocked from iOS 26.2 beta 2 upward — the
same fail-closed boundary as MobileGestalt (open through iOS 26.2 beta 1
/ build 23C5027f, locked from build 23C5035e, 23G82/23G83 included).

The fix lives in the gating layer only (payload definitions untouched):
``capabilities.tweak_deliverability`` now evaluates the eligibility
files-based family against the SAME shared ``mobilegestalt_decision``,
the loader never registers those tweaks as deliverable on a locked or
unknown device, the shared clearer force-disables stale enabled state,
and the Eligibility section locks its switches with an explanation.

Run from the repo root with the isolated venv + isolated HOME:

    QT_QPA_PLATFORM=offscreen HOME=<tmp> ~/workspace/.venv-ws11/bin/python \
        tools/test_eligibility_boundary.py
"""
import os
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_results = {"passed": 0, "failed": 0}


def check(name, condition, detail=""):
    if condition:
        _results["passed"] += 1
        print(f"  PASS: {name}")
    else:
        _results["failed"] += 1
        print(f"  FAIL: {name}  {detail}")


ELIG_IDS = None  # filled in main() after imports


def test_deliverability_matrix():
    print("== tweak_deliverability: Eligibility build matrix ==")
    from src.tweaks.tweak_names import TweakID
    from src.tweaks.capabilities import (
        ELIGIBILITY_LOCKED_MESSAGE, requires_eligibility_boundary,
        tweak_deliverability,
    )

    for tid in (TweakID.EUEnabler, TweakID.AIEligibility, TweakID.CreateBRFolders):
        check(f"{tid.name} classified in the eligibility boundary family",
              requires_eligibility_boundary(tid))

    # (build, version, expected deliverable, note)
    matrix = [
        ("23C5027f", "26.2", True, "iOS 26.2 beta 1: last supported build"),
        ("23C5035e", "26.2", False, "iOS 26.2 beta 2: lock starts here"),
        ("23G82", "26.6.1", False, "iOS 26.6.1 build 23G82 locked"),
        ("23G83", "26.6.1", False, "iOS 26.6.1 RC build 23G83 locked"),
        ("", "", False, "no device evidence: fail-closed"),
        ("", "26.1", True, "version-only fallback below 26.2 stays open"),
        ("", "26.6.1", False, "version-only fallback 26.2+ stays locked"),
    ]
    for tid in (TweakID.EUEnabler, TweakID.AIEligibility, TweakID.CreateBRFolders):
        for build, version, expected, note in matrix:
            ok, code, msg = tweak_deliverability(
                tid, device_version=version, device_build=build)
            check(f"{tid.name} build={build or '-'} version={version or '-'} "
                  f"deliverable={expected} ({note})",
                  ok == expected,
                  f"got deliverable={ok} reason={code} msg={msg!r}")
            if not expected:
                check(f"{tid.name} build={build or '-'} lock carries an explanation",
                      bool(msg) and (msg == ELIGIBILITY_LOCKED_MESSAGE
                                     or "26.2 beta" in msg),
                      f"msg={msg!r}")

    # The shared boundary must agree with the MobileGestalt family itself:
    # same builds, same decision, no second version logic.
    from src.devicemanagement.constants import mobilegestalt_decision
    for build, version, expected, _note in matrix:
        ok, _code, _msg = tweak_deliverability(
            TweakID.EUEnabler, device_version=version, device_build=build)
        check(f"Eligibility boundary == shared decision at {build or version}",
              ok == mobilegestalt_decision(build, version).supported)

    # Overreach guard: an ordinary non-gated tweak is NOT blocked by the
    # new gate on the locked 26.6.1 build.
    ok, code, _msg = tweak_deliverability(
        TweakID.AnimDragCoeff, device_version="26.6.1", device_build="23G83")
    check("Ordinary tweak (AnimDragCoeff) stays deliverable on 23G83",
          ok, f"reason={code}")
    # And the MobileGestalt family is untouched by the new family set.
    ok, _code, msg = tweak_deliverability(
        TweakID.DynamicIsland, device_version="26.6.1", device_build="23G83")
    check("MobileGestalt family still locked on 23G83 with gestalt wording",
          not ok and "MobileGestalt" in msg, f"msg={msg!r}")


def _fake_device(build, version):
    return SimpleNamespace(build=build, version=version,
                           model="iPhone16,1", hardware="D83AP", cpu="t8130")


def test_loader_matrix():
    print("== load_eligibility: registration follows the shared decision ==")
    from src.devicemanagement.constants import mobilegestalt_decision
    from src.tweaks.tweaks import tweaks, TweakID
    from src.tweaks.tweak_loader import load_eligibility

    touched = (TweakID.EUEnabler, TweakID.AIEligibility, TweakID.CreateBRFolders,
               TweakID.SpoofModel, TweakID.SpoofHardware, TweakID.SpoofCPU,
               TweakID.AIGestalt)
    saved = {tid: tweaks.get(tid) for tid in touched}
    saved_enabled = {tid: (getattr(tweaks.get(tid), "enabled", False))
                     for tid in touched}
    try:
        # --- locked device (26.6.1 RC): nothing eligibility registers ---
        for tid in (TweakID.EUEnabler, TweakID.AIEligibility):
            tweaks.pop(tid, None)
        load_eligibility(_fake_device("23G83", "26.6.1"),
                         mobilegestalt_decision("23G83", "26.6.1"))
        check("Locked 23G83: EUEnabler never registered",
              TweakID.EUEnabler not in tweaks)
        check("Locked 23G83: AIEligibility never registered",
              TweakID.AIEligibility not in tweaks)
        check("Locked 23G83: SpoofModel never registered",
              TweakID.SpoofModel not in tweaks)

        # --- stale enabled state from a supported session is forced off ---
        from src.tweaks.eligibility_tweak import EligibilityTweak
        stale = EligibilityTweak()
        stale.set_enabled(True)
        tweaks[TweakID.EUEnabler] = stale
        br = tweaks.get(TweakID.CreateBRFolders)
        if br is not None:
            br.set_enabled(True)
        load_eligibility(_fake_device("23G83", "26.6.1"),
                         mobilegestalt_decision("23G83", "26.6.1"))
        check("Locked 23G83: stale enabled EUEnabler forced off",
              tweaks[TweakID.EUEnabler].enabled is False)
        check("Locked 23G83: stale enabled CreateBRFolders forced off",
              br is None or br.enabled is False)

        # --- supported device (26.2 beta 1): everything registers ---
        for tid in (TweakID.EUEnabler, TweakID.AIEligibility):
            tweaks.pop(tid, None)
        load_eligibility(_fake_device("23C5027f", "26.2"),
                         mobilegestalt_decision("23C5027f", "26.2"))
        check("Supported 23C5027f: EUEnabler registered",
              TweakID.EUEnabler in tweaks)
        check("Supported 23C5027f: AIEligibility registered",
              TweakID.AIEligibility in tweaks)
        check("Supported 23C5027f: SpoofModel registered",
              TweakID.SpoofModel in tweaks)
    finally:
        for tid in touched:
            if saved[tid] is None:
                tweaks.pop(tid, None)
            else:
                tweaks[tid] = saved[tid]
                try:
                    tweaks[tid].set_enabled(saved_enabled[tid])
                except Exception:
                    tweaks[tid].enabled = saved_enabled[tid]


def test_ui_locks():
    print("== EligibilitySection: switches lock on locked builds ==")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    from src.gui.ios.eligibility import EligibilitySection
    from src.tweaks.tweaks import tweaks, TweakID

    def make_section(build, version):
        dev = _fake_device(build, version)
        window = SimpleNamespace(device_manager=SimpleNamespace(
            data_singleton=SimpleNamespace(current_device=dev)))
        section = EligibilitySection(window)
        section.refresh()
        return section

    locked = make_section("23G83", "26.6.1")
    for tid, label in ((TweakID.EUEnabler, "EU Enabler"),
                       (TweakID.CreateBRFolders, "folder"),
                       ("elig_file_group", "eligibility-file group")):
        sw = locked._switches.get(tid)
        check(f"Locked 23G83: {label} switch disabled",
              sw is not None and not sw.isEnabled())
    eu_card = locked._cards.get(TweakID.EUEnabler)
    check("Locked 23G83: EU Enabler card shows the lock explanation",
          eu_card is not None and "26.2 beta 2" in eu_card.toolTip(),
          f"tooltip={eu_card.toolTip() if eu_card else None!r}")

    # State-level guard: a programmatic ON attempt cannot enable it.
    before = tweaks.get(TweakID.EUEnabler)
    if before is not None:
        before.set_enabled(False)
    locked._on_switch(TweakID.EUEnabler, True)
    check("Locked 23G83: _on_switch guard keeps EUEnabler off",
          TweakID.EUEnabler not in tweaks
          or tweaks[TweakID.EUEnabler].enabled is False)

    supported = make_section("23C5027f", "26.2")
    sw = supported._switches.get(TweakID.EUEnabler)
    check("Supported 23C5027f: EU Enabler switch enabled",
          sw is not None and sw.isEnabled())
    eu_card = supported._cards.get(TweakID.EUEnabler)
    check("Supported 23C5027f: EU Enabler card has no lock tooltip",
          eu_card is not None and eu_card.toolTip() == "")
    app.processEvents()


def main():
    test_deliverability_matrix()
    test_loader_matrix()
    test_ui_locks()
    print(f"\n{_results['passed']} passed, {_results['failed']} failed")
    return 1 if _results["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
