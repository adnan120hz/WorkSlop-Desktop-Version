"""``Nugget reset`` — reset tweak sections back to defaults (the GUI's
"Reset Tweaks" flow).

Restores stock values for the selected sections straight to the device.
"""

import argparse
import sys

from src.utils.pages import Page


def add_parser(subp):
    parser = subp.add_parser(
        "reset",
        help="Reset tweak sections to defaults",
        description="Restore stock values for the selected sections "
                    "(uses the same reset + restore path as the GUI).",
    )
    parser.add_argument("--udid", default=None, help="target device UDID")
    parser.add_argument("--status-bar", action="store_true",
                        help="reset the Status Bar section")
    parser.add_argument("--springboard", action="store_true",
                        help="reset the SpringBoard section")
    parser.add_argument("--daemons", action="store_true",
                        help="reset the Daemons section")
    parser.add_argument("--internal", action="store_true",
                        help="reset the Internal Options section")
    parser.add_argument("--no-skip-setup", action="store_true",
                        help="don't mark iOS setup panes complete")
    parser.add_argument("--no-reboot", action="store_true",
                        help="don't auto-reboot after resetting")
    parser.set_defaults(func=run)
    return parser


def _resolve_pages(args, dm) -> list:
    from src.utils.pages import get_resettable_pages
    explicit = []
    if args.status_bar:
        explicit.append(Page.StatusBar)
    if args.springboard:
        explicit.append(Page.Springboard)
    if args.daemons:
        explicit.append(Page.Daemons)
    if args.internal:
        explicit.append(Page.InternalOptions)
    if explicit:
        return explicit
    pages = get_resettable_pages(dm)
    last = ""
    if pages:
        last = pages[-1].getPageName()
    print(f"Resetting all resettable sections "
          f"({', '.join(p.getPageName() for p in pages)}).")
    return pages


def run(args) -> int:
    from src.cli.common import (
        bootstrap, make_device_manager, load_prefs, ensure_device,
        ensure_not_killed, print_status, print_alert, describe_device)

    settings = bootstrap()
    dm = make_device_manager(settings)
    load_prefs(dm, settings)
    if args.no_skip_setup:
        dm.pref_manager.skip_setup = False
    if args.no_reboot:
        dm.pref_manager.auto_reboot = False

    device = ensure_device(dm, settings, args.udid)
    print("Device:", describe_device(device))
    # HotLoad kill_app gate: the GUI refuses to start on a killed
    # device/iOS; the CLI must refuse before doing device work too.
    ensure_not_killed(settings, device=device, dm=dm)

    pages = _resolve_pages(args, dm)
    print("Starting reset...")
    # Honest exit code (Fix Audit 44): the backend reports failure through
    # the final alert instead of raising (same contract as `Nugget apply`),
    # so track the last alert and fail the process when it is not the
    # success one. Previously this always returned 0, even on failure.
    _last_alert = {}

    def _show_alert(msg):
        print_alert(msg)
        _last_alert["msg"] = msg

    try:
        dm.reset_tweaks(pages, settings,
                        update_label=print_status,
                        show_alert=_show_alert)
    except Exception as e:
        print(f"ERROR: reset failed: {e}", file=sys.stderr)
        return 1
    if getattr(dm, "last_apply_journal_path", None):
        print(f"Apply journal: {dm.last_apply_journal_path}")
    final = _last_alert.get("msg")
    failed = final is not None and getattr(final, "title", None) != "Success!"
    if failed:
        print("Reset FAILED (see the error above).", file=sys.stderr)
        return 1
    print("Reset finished.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_parser(parser)
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())