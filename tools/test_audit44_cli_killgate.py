#!/usr/bin/env python3
"""Fix Audit 44: CLI must not bypass the HotLoad kill_app gate.

* ``ensure_not_killed`` (src/cli/common.py) asks the same
  ``HotLoad.kill_rule`` the GUI checks at startup and exits non-zero
  BEFORE any device work when a kill rule matches this device/iOS;
* ``Nugget reset`` returns a non-zero exit code when the backend's
  final alert is not the success one (it used to always return 0);
* ``Nugget hotload refresh`` with HotLoad OFF is an honest no-op
  ("HotLoad is off — nothing fetched", exit 0) instead of pretending
  to fetch / reporting a fake fetch failure.

Offline: every device/settings/HotLoad collaborator is faked, no
device or network is touched.

Run: QT_QPA_PLATFORM=offscreen python tools/test_audit44_cli_killgate.py
"""
import argparse
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


class FakeDevice:
    name = "Fake iPhone"
    version = "26.6.1"
    build = "23G83"
    model = "iPhone14,5"
    udid = "FAKE-UDID"


class FakeAlert:
    def __init__(self, title, txt=""):
        self.title = title
        self.txt = txt or title


class FakeDM:
    """DeviceManager stand-in: records whether device work started."""

    def __init__(self, alert=None, raises=False):
        self.pref_manager = argparse.Namespace(
            settings=None, skip_setup=True, auto_reboot=True)
        self.last_apply_journal_path = None
        self._alert = alert
        self._raises = raises
        self.reset_called = False

    def get_current_device_version(self):
        return FakeDevice.version

    def get_current_device_model(self):
        return FakeDevice.model

    def reset_tweaks(self, pages, settings, update_label=None, show_alert=None):
        self.reset_called = True
        if self._raises:
            raise RuntimeError("backend exploded")
        if show_alert is not None and self._alert is not None:
            show_alert(self._alert)


def test_real_hotload_kill_matching():
    print("\nHotLoad.kill_rule: the shared rule logic itself")
    from src.controllers.hotload import HotLoad
    hl = object.__new__(HotLoad)
    hl.settings = None  # is_enabled() -> True when no settings store
    hl._rules = {"version": 1, "rules": [
        {"action": "kill_app", "reason": "iOS 26.6.1 blocked for safety",
         "min_version": "26.0", "max_version": "26.6.1",
         "only_models": ["iPhone14"]}]}
    check("kill rule matches in-scope device/iOS",
          hl.kill_rule("26.6.1", "iPhone14,5") is not None)
    check("no kill outside the iOS range",
          hl.kill_rule("16.0", "iPhone14,5") is None)
    check("no kill for another model family",
          hl.kill_rule("26.6.1", "iPad13,1") is None)
    hl._rules = {"version": 1, "rules": [
        {"action": "kill_app", "disabled": False}]}
    check("disabled=false rule never applies",
          hl.kill_rule("26.6.1", "iPhone14,5") is None)


def test_ensure_not_killed_gate():
    print("\nensure_not_killed: CLI gate refuses before device work")
    import src.controllers.hotload as hotload_mod
    from src.cli import common

    seen = {}

    class FakeHotLoad:
        def __init__(self, settings):
            pass

        def kill_rule(self, version=None, model=None):
            seen["args"] = (version, model)
            return seen["kill"]

    real = hotload_mod.HotLoad
    hotload_mod.HotLoad = FakeHotLoad
    try:
        seen["kill"] = {"reason": "blocked by safety rules"}
        try:
            common.ensure_not_killed(object(), device=FakeDevice())
            raised = None
        except SystemExit as e:
            raised = e.code
        check("kill rule -> SystemExit(1)", raised == 1, repr(raised))
        check("gate asked with this device's iOS + model",
              seen["args"] == ("26.6.1", "iPhone14,5"), repr(seen["args"]))

        seen["kill"] = None
        check("no kill rule -> gate passes silently",
              common.ensure_not_killed(object(), device=FakeDevice()) is None)
    finally:
        hotload_mod.HotLoad = real


def _run_reset_with(dm, gate_raises=False):
    """Drive cmd_reset.run with faked collaborators; return (code, stdout)."""
    from src.cli import cmd_reset, common

    def fake_gate(settings, device=None, dm=None):
        if gate_raises:
            raise SystemExit(1)

    saved = {name: getattr(common, name) for name in
             ("bootstrap", "make_device_manager", "load_prefs",
              "ensure_device", "ensure_not_killed")}
    common.bootstrap = lambda: object()
    common.make_device_manager = lambda settings: dm
    common.load_prefs = lambda dm_, settings: None
    common.ensure_device = lambda dm_, settings, udid=None: FakeDevice()
    common.ensure_not_killed = fake_gate
    args = argparse.Namespace(udid=None, no_skip_setup=False,
                              no_reboot=False, status_bar=True,
                              springboard=False, daemons=False,
                              internal=False)
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(io.StringIO()):
            try:
                code = cmd_reset.run(args)
            except SystemExit as e:
                code = ("SystemExit", e.code)
    finally:
        for name, fn in saved.items():
            setattr(common, name, fn)
    return code, out.getvalue()


def test_cmd_reset():
    print("\ncmd_reset: kill gate first, honest exit codes after")

    dm = FakeDM(alert=FakeAlert("Success!"))
    code, _ = _run_reset_with(dm, gate_raises=True)
    check("kill gate -> reset refuses (SystemExit 1)",
          code == ("SystemExit", 1), repr(code))
    check("kill gate -> no device work started", not dm.reset_called)

    dm = FakeDM(alert=FakeAlert("Error!", "restore failed hard"))
    code, _ = _run_reset_with(dm)
    check("backend failure alert -> exit 1", code == 1, repr(code))
    check("reset actually ran when not killed", dm.reset_called)

    dm = FakeDM(alert=FakeAlert("Success!"))
    code, out = _run_reset_with(dm)
    check("success alert -> exit 0", code == 0, repr(code))
    check("success still announced", "Reset finished." in out)

    dm = FakeDM(raises=True)
    code, _ = _run_reset_with(dm)
    check("backend exception -> exit 1 (no traceback escape)",
          code == 1, repr(code))


def test_hotload_refresh_honesty():
    print("\ncmd_hotload refresh: honest when OFF")
    from src.cli import cmd_hotload

    class FakeHotLoad:
        def __init__(self, enabled, ok):
            self._enabled = enabled
            self._ok = ok
            self.update_called = False

        def is_enabled(self):
            return self._enabled

        def update(self, url=None):
            self.update_called = True
            return self._ok

    saved_settings, saved_hotload = cmd_hotload._settings, cmd_hotload._hotload
    try:
        fake = FakeHotLoad(enabled=False, ok=True)
        cmd_hotload._settings = lambda: object()
        cmd_hotload._hotload = lambda settings: fake
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cmd_hotload._run_refresh(argparse.Namespace(url="x"))
        check("OFF -> exit 0 (no-op, not a fetch failure)", code == 0)
        check("OFF -> nothing was fetched", not fake.update_called)
        check("OFF -> honest message",
              "HotLoad is off" in out.getvalue()
              and "nothing fetched" in out.getvalue(),
              out.getvalue().strip())

        fake = FakeHotLoad(enabled=True, ok=False)
        cmd_hotload._hotload = lambda settings: fake
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            code = cmd_hotload._run_refresh(argparse.Namespace(url="x"))
        check("ON + fetch failure -> exit 1", code == 1)
        check("ON -> fetch was attempted", fake.update_called)
    finally:
        cmd_hotload._settings, cmd_hotload._hotload = saved_settings, saved_hotload


def main():
    test_real_hotload_kill_matching()
    test_ensure_not_killed_gate()
    test_cmd_reset()
    test_hotload_refresh_honesty()
    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
