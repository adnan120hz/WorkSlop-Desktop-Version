#!/usr/bin/env python3
"""Round-4 audit regressions: NameError paths pyflakes exposed.

* ``PBDBThread.run()`` called ``install_windows_selector_policy`` with
  no import — the PosterBoard database backup thread died instantly.
* ``web_request_handler.get_latest_version`` used ``App_Version`` /
  ``App_Build`` with no import in scope.
* grappa's ``_cf_dictionary`` used ``ctypes`` imported only inside a
  sibling function (macOS-only path; pinned by source inspection here).

Run: python tools/test_audit_round4_regressions.py
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def main():
    print("\nround-4 NameError regressions")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    # PBDBThread.run must reach the backup function (previously raised
    # NameError before the try block and the backup never started).
    from src.gui.thread_workers.pb_worker import PBDBThread
    ran = []
    thread = PBDBThread(lambda label, progress: ran.append(True))
    thread.run()  # synchronous: run() is the thread body
    check("PBDBThread.run executes the backup function", ran == [True])

    # get_latest_version must resolve the version constants.
    from src.controllers import web_request_handler as wrh
    fake = types.SimpleNamespace(
        outcome="no_update",
        latest=types.SimpleNamespace(version="9.9.9"))
    original = wrh.check_for_update
    wrh.check_for_update = lambda v, b, c: fake
    try:
        got = wrh.get_latest_version()
    finally:
        wrh.check_for_update = original
    check("get_latest_version returns the stripped tag", got == "9.9.9")

    # grappa: the ctypes import must live inside _cf_dictionary itself.
    import inspect
    from src.airlift import grappa
    src = inspect.getsource(grappa._cf_dictionary)
    check("grappa._cf_dictionary imports ctypes locally",
          "import ctypes" in src)

    print(f"\nALL {PASS} CHECKS PASSED")


if __name__ == "__main__":
    main()
