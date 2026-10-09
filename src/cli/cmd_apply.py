"""``Nugget apply`` — run the full tweak apply flow (the GUI's "Apply" page).

Starts from the auto-saved preset (or ``--preset``), lets extra ``--enable`` /
``--disable`` / ``--set`` / ``--daemon-*`` flags be mixed in on the command
line, then applies everything to the device over lockdown.
"""

import argparse
import sys


def add_parser(subp):
    parser = subp.add_parser(
        "apply",
        help="Apply the current tweak state to the device",
        description="Generate everything enabled in the tweak state and restore "
                    "it to the device (exactly what the GUI's Apply button runs). "
                    "Takes the state from AutoSave (or --preset) plus any "
                    "--enable/--disable/--set/--daemon-* overrides.",
    )
    parser.add_argument("--udid", default=None, help="target device UDID")
    parser.add_argument("--preset", default=None,
                        help="preset to start from (default: AutoSave)")
    parser.add_argument("--enable", action="append", default=[], metavar="ID",
                        help="enable a registry tweak first (repeatable)")
    parser.add_argument("--disable", action="append", default=[], metavar="ID",
                        help="disable a registry tweak first (repeatable)")
    parser.add_argument("--set", action="append", default=[], metavar="ID=VALUE",
                        help="set a tweak's value (enables it)")
    parser.add_argument("--daemon-disable", action="append", default=[],
                        metavar="DAEMON", help="disable a daemon first (repeatable)")
    parser.add_argument("--daemon-enable", action="append", default=[],
                        metavar="DAEMON", help="re-enable a daemon first (repeatable)")
    parser.add_argument("--encrypted-backup", action="store_true",
                        help="use encrypted backups (needs --password)")
    parser.add_argument("--password", default=None,
                        help="backup password for encrypted restores")
    parser.add_argument("--no-skip-setup", action="store_true",
                        help="don't mark iOS setup panes complete (default: skip)")
    parser.add_argument("--no-reboot", action="store_true",
                        help="don't auto-reboot the device after applying")
    parser.add_argument("--continue-anyway", action="store_true",
                        help="continue without a protective backup when the "
                             "device/computer is low on disk space (data risk)")
    parser.set_defaults(func=run)
    return parser


def _apply_flag_tweaks(args):
    from src.cli.cmd_tweaks import _resolve_specs, _coerce_cli_value
    from src.tweaks.tweaks import tweaks

    for name in args.enable:
        for spec in _resolve_specs([name]):
            tweaks[spec.id].set_enabled(True)
            print(f"[apply] enabled {spec.id.name}")
    for name in args.disable:
        for spec in _resolve_specs([name]):
            tweaks[spec.id].set_enabled(False)
            print(f"[apply] disabled {spec.id.name}")
    for item in args.set:
        if "=" not in item:
            print(f"ERROR: --set expects ID=VALUE, got '{item}'.", file=sys.stderr)
            raise SystemExit(2)
        name, _, value = item.partition("=")
        spec = _resolve_specs([name])[0]
        value, error = _coerce_cli_value(spec, value)
        if error is not None:
            print(f"ERROR: {error}", file=sys.stderr)
            raise SystemExit(2)
        tweaks[spec.id].set_value(value, toggle_enabled=True)
        print(f"[apply] set {spec.id.name} = {value!r}")

    if args.daemon_disable or args.daemon_enable:
        from src.cli.cmd_daemons import _resolve_daemons, _set_keys
        from src.tweaks.tweak_loader import load_daemons
        from src.tweaks.tweaks import TweakID
        load_daemons()
        dl = tweaks[TweakID.Daemons]
        for name in args.daemon_disable:
            dl.set_enabled(True)
            for d in _resolve_daemons([name]):
                keys = _set_keys(d, True)
                print(f"[apply] disabled daemon {name} -> {', '.join(keys)}")
        for name in args.daemon_enable:
            for d in _resolve_daemons([name]):
                keys = _set_keys(d, False)
                print(f"[apply] enabled daemon {name} -> {', '.join(keys)}")


def run(args) -> int:
    from src.cli.common import (
        bootstrap, make_device_manager, load_prefs, ensure_device,
        ensure_not_killed, print_status,
        print_alert, describe_device, load_core_tweaks, load_default_preset)

    settings = bootstrap()
    dm = make_device_manager(settings)
    load_prefs(dm, settings)
    if args.no_skip_setup:
        dm.pref_manager.skip_setup = False
    if args.no_reboot:
        dm.pref_manager.auto_reboot = False
    if args.encrypted_backup:
        dm.pref_manager.use_encrypted_backup = True

    device = ensure_device(dm, settings, args.udid)
    print("Device:", describe_device(device))
    # HotLoad kill_app gate: same rule the GUI enforces at startup — refuse
    # before any device work when this device/iOS is killed (Fix Audit 44).
    ensure_not_killed(settings, device=device, dm=dm)

    load_core_tweaks()
    load_default_preset(args.preset, dm)
    _apply_flag_tweaks(args)

    def prompt_password(title, text):
        if args.password:
            return args.password
        raise RuntimeError(
            "Backup password required for an encrypted restore. "
            "Re-run with --password <your iCloud backup password>.")

    if args.continue_anyway:
        _auto_resumes = {"count": 0}

        def prompt_choice(title, text):
            # Bounded auto-resume (84% hang fix): --continue-anyway used to
            # answer "resume" forever, making CLI applies literally
            # unbounded. One automatic resume keeps the convenience
            # without the infinite loop.
            _auto_resumes["count"] += 1
            if _auto_resumes["count"] > 1:
                print(f"[warning] {title}: auto-resume limit reached; aborting.")
                return "abort"
            print(f"[warning] {title}: {text}")
            print("[warning] continuing WITHOUT data protection (--continue-anyway)")
            return "resume"
    else:
        prompt_choice = None

    print("Starting apply...")
    # Honest exit code: the backend reports failure through the final
    # alert instead of raising (show_apply_error), so track the last
    # alert and fail the process when it is not the success one
    # (audit round 23 — scripts check $?).
    _last_alert = {}

    def _show_alert(msg):
        print_alert(msg)
        _last_alert["msg"] = msg

    # Same honest-exit-code pattern as cmd_reset (Fix Audit 44): a
    # raised backend error is exit 1, and so is any final alert that is
    # not the success one (abort included — the backend now surfaces an
    # explicit "Apply Aborted" alert, Fix Audit 54). No final alert at
    # all means success was never reported, so that is not exit 0.
    try:
        dm.apply_changes(update_label=print_status,
                         show_alert=_show_alert,
                         prompt_password=prompt_password,
                         prompt_choice=prompt_choice)
    except Exception as e:
        print(f"ERROR: apply failed: {e}", file=sys.stderr)
        return 1
    if getattr(dm, "last_apply_journal_path", None):
        print(f"Apply journal: {dm.last_apply_journal_path}")
    final = _last_alert.get("msg")
    failed = final is None or getattr(final, "title", None) != "Success!"
    if failed:
        print("Apply FAILED or ABORTED (see the message above).",
              file=sys.stderr)
        return 1
    print("Apply finished.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.set_defaults(func_run=True)
    add_parser(parser)
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())