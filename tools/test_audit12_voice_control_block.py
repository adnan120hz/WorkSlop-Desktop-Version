#!/usr/bin/env python3
"""Fix Audit 12: the Voice Control hard-block must be REAL.

The claim used to be theater: Daemon.VoiceControl had a "Disable Voice
Control" switch on the Daemons page, and an enabled state flowed through
presets and the CLI into disabled.plist. This test proves the gate now
holds at every entry point, while every other daemon's payload is
untouched:

* core: ``BLOCKED_DAEMONS`` feeds ``never_enable``, so the Daemons tweak
  can never store or apply the Voice Control keys;
* UI: flipping the Voice Control switch is refused with the honest
  reason (bootloop risk) and the switch snaps back off;
* preset: a stored preset asking for Voice Control is neutralised on
  load — keys dropped, skip recorded in ``last_skipped`` — while other
  daemons in the same preset still load;
* CLI: ``daemons disable VoiceControl`` / raw launchd keys and the
  ``apply --daemon-disable`` path exit non-zero with the honest reason;
  re-enabling (value False) stays allowed.

Offline: no device, no network. Run:
QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python tools/test_audit12_voice_control_block.py
"""
import argparse
import contextlib
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def test_core_gate():
    print("\ncore: never_enable gate on the Daemons tweak")
    from src.tweaks.daemons_tweak import (
        Daemon, BLOCKED_DAEMONS, BLOCKED_DAEMON_KEYS, DANGEROUS_KEYS,
        VOICE_CONTROL_BLOCK_REASON)
    from src.tweaks.tweak_loader import load_daemons
    from src.tweaks.tweaks import tweaks, TweakID
    from src.tweaks.basic_plist_locations import FileLocation

    check("VoiceControl is the blocked daemon",
          BLOCKED_DAEMONS == frozenset({Daemon.VoiceControl}))
    check("blocked keys are the Voice Control launchd keys",
          BLOCKED_DAEMON_KEYS == frozenset(Daemon.VoiceControl.value),
          str(sorted(BLOCKED_DAEMON_KEYS)))
    check("reason is honest (bootloop risk, blocked)",
          "blocked" in VOICE_CONTROL_BLOCK_REASON
          and "bootloop" in VOICE_CONTROL_BLOCK_REASON)

    load_daemons()
    dl = tweaks[TweakID.Daemons]
    dl.set_enabled(False)
    for k in list(dl.value):
        dl.value[k] = False
    check("blocked keys feed the tweak's never_enable set",
          BLOCKED_DAEMON_KEYS <= set(dl.never_enable)
          and BLOCKED_DAEMON_KEYS == DANGEROUS_KEYS)

    dl.set_multiple_values(Daemon.VoiceControl.value, value=True)
    check("set_multiple_values(True) cannot store Voice Control",
          not any(dl.value.get(k) for k in Daemon.VoiceControl.value))

    # payload gate: even a hand-corrupted value dict loses the keys
    dl.value["com.apple.assistantd"] = True
    dl.value["com.apple.tipsd"] = True
    dl.set_enabled(True)
    payload = dl.apply_tweak({})
    staged = payload.get(FileLocation.disabledDaemons, {})
    check("apply payload drops Voice Control keys",
          "com.apple.assistantd" not in staged
          and "com.apple.voiced" not in staged
          and "com.apple.assistant_service" not in staged,
          str(sorted(staged)))
    check("other daemon payload untouched (tipsd still applies)",
          staged.get("com.apple.tipsd") is True)
    dl.set_enabled(False)
    dl.value.pop("com.apple.assistantd", None)
    dl.value["com.apple.tipsd"] = False


def test_ui_gate():
    print("\nUI: Daemons page refuses the Voice Control switch")
    import src.gui.ios.daemons as daemons_page
    from src.gui.ios.daemons import IOSDaemonsContent
    from src.tweaks.daemons_tweak import Daemon
    from src.tweaks.tweak_loader import load_daemons
    from src.tweaks.tweaks import tweaks, TweakID

    load_daemons()
    dl = tweaks[TweakID.Daemons]
    dl.set_enabled(False)

    warnings = []
    orig_warning = daemons_page.QMessageBox.warning
    daemons_page.QMessageBox.warning = staticmethod(
        lambda *a, **k: warnings.append(a))
    try:
        class FakeDM:
            def get_current_device_version(self):
                return "26.2"

            def get_current_device_model(self):
                return "iPhone17,1"

        class FakeWindow:
            def __init__(self):
                from PySide6.QtCore import QSettings
                self.settings = QSettings("GoldenNuggetTest", "Audit12VC")
                self.settings.setValue("daemon_bootloop_warned", True)
                self.settings.sync()
                self.device_manager = FakeDM()

        content = IOSDaemonsContent(FakeWindow())
        vc_switch = dict(content.daemon_switches)[Daemon.VoiceControl]
        check("Voice Control switch starts off", not vc_switch.isChecked())

        # a real user click path: setChecked(True) fires the handler
        vc_switch.setChecked(True)
        check("switch snaps back off after a forced ON",
              not vc_switch.isChecked())
        check("honest reason dialog shown exactly once",
              len(warnings) == 1
              and "bootloop" in str(warnings[0][-1]),
              str(warnings))
        check("tweak value never stored Voice Control",
              not any(dl.value.get(k) for k in Daemon.VoiceControl.value))

        # refresh (e.g. after a preset load) never paints it ON either
        dl.value["com.apple.voiced"] = True
        content.refresh_from_tweaks()
        check("refresh_from_tweaks forces the switch off",
              not vc_switch.isChecked())
        dl.value.pop("com.apple.voiced", None)
    finally:
        daemons_page.QMessageBox.warning = orig_warning


def test_preset_gate():
    print("\npreset: stored Voice Control state is neutralised with a note")
    from src.controllers.preset_manager import PresetManager
    from src.tweaks.tweak_loader import load_daemons
    from src.tweaks.tweaks import tweaks, TweakID

    tmp = tempfile.mkdtemp(prefix="audit12-")
    pm = PresetManager()
    pm.presets_dir = tmp
    preset = {
        "metadata": {"version": 2},
        "tweaks": {
            "Daemons": {
                "type": "AdvancedPlistTweak", "enabled": True,
                "value": {
                    "com.apple.assistant_service": True,
                    "com.apple.assistantd": True,
                    "com.apple.voiced": True,
                    "com.apple.tipsd": True,
                },
            }
        },
    }
    with open(pm.get_preset_path("vc"), "w", encoding="utf-8") as f:
        json.dump(preset, f)

    load_daemons()
    dl = tweaks[TweakID.Daemons]
    ok = pm.load_preset("vc")
    check("preset still loads (other tweaks unaffected)", ok is True)
    check("Voice Control keys dropped on load",
          not any(dl.value.get(k) for k in (
              "com.apple.assistant_service", "com.apple.assistantd",
              "com.apple.voiced")),
          str(dl.value))
    check("other daemon in the same preset still loads",
          dl.value.get("com.apple.tipsd") is True)
    skipped = [s for s in pm.last_skipped
               if s.get("reason_code") == "VOICE_CONTROL_BLOCKED"]
    check("skip recorded in last_skipped with the honest reason",
          len(skipped) == 1 and "bootloop" in skipped[0]["reason"],
          str(pm.last_skipped))
    dl.set_enabled(False)
    dl.value["com.apple.tipsd"] = False

    # a fresh save can never write the blocked keys back out
    dl.set_multiple_values(["com.apple.voiced"], value=True)
    data = pm._serialize()
    saved = data["tweaks"]["Daemons"]["value"]
    check("serialize never writes Voice Control keys",
          "com.apple.voiced" not in saved, str(sorted(saved)))


def test_cli_gate():
    print("\nCLI: daemon disable + apply flag paths refuse, exit non-zero")
    from src.cli import cmd_daemons, cmd_apply
    from src.tweaks.daemons_tweak import Daemon
    from src.tweaks.tweak_loader import load_daemons
    from src.tweaks.tweaks import tweaks, TweakID

    load_daemons()
    dl = tweaks[TweakID.Daemons]

    err = io.StringIO()
    code = None
    with contextlib.redirect_stderr(err):
        try:
            cmd_daemons._set_keys(Daemon.VoiceControl, True)
        except SystemExit as e:
            code = e.code
    check("daemons disable VoiceControl exits non-zero", code == 1,
          f"code={code}")
    check("CLI error carries the honest reason",
          "bootloop" in err.getvalue(), err.getvalue().strip()[:80])
    check("no state stored by the refused CLI disable",
          not any(dl.value.get(k) for k in Daemon.VoiceControl.value))

    code = None
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            cmd_daemons._set_keys("com.apple.voiced", True)
        except SystemExit as e:
            code = e.code
    check("raw launchd key com.apple.voiced is refused too", code == 1)

    args = argparse.Namespace(names=["VoiceControl"], no_save=True)
    code = None
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            cmd_daemons._run_disable(args)
        except SystemExit as e:
            code = e.code
    check("`daemons disable` command exits non-zero", code == 1)

    apply_args = argparse.Namespace(
        enable=[], disable=[], set=[],
        daemon_disable=["VoiceControl"], daemon_enable=[])
    code = None
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            cmd_apply._apply_flag_tweaks(apply_args)
        except SystemExit as e:
            code = e.code
    check("`apply --daemon-disable VoiceControl` exits non-zero", code == 1)

    # re-enabling (turning the disable OFF) is not a disable attempt
    keys = cmd_daemons._set_keys(Daemon.VoiceControl, False)
    check("re-enable path still allowed",
          keys == Daemon.VoiceControl.value)

    # positive control: an ordinary daemon still disables fine
    keys = cmd_daemons._set_keys(Daemon.Tips, True)
    check("ordinary daemon (Tips) still settable via CLI",
          dl.value.get("com.apple.tipsd") is True and keys == Daemon.Tips.value)
    dl.set_enabled(False)
    dl.value["com.apple.tipsd"] = False


def main():
    test_core_gate()
    test_ui_gate()
    test_preset_gate()
    test_cli_gate()
    print(f"\nPASS {PASS} checks — Voice Control block is real on "
          f"core/UI/preset/CLI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
