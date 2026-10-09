#!/usr/bin/env python3
"""Fix Audit 84 (remainder): thread crashes + relaunch failure logging.

* ``install_crash_handler`` now also installs ``threading.excepthook``:
  a worker-thread crash leaves a session-log record naming the thread
  and is routed into the same crash path as a main-thread exception,
  while ``sys.excepthook`` keeps its existing handler.
* ``_restart_app``'s relaunch ``except: pass`` now logs; behaviour
  (never raise from the crash path) is unchanged.

Run: QT_QPA_PLATFORM=offscreen ~/wsvenv/bin/python \
    tools/test_audit84_thread_crash.py
"""
import logging
import os
import sys
import threading
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


import src.exceptions.crash_handler as ch  # noqa: E402


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


print("\nthread excepthook routes thread crashes to the crash path")
logger = logging.getLogger("WorkSlop.crash")
cap = Capture()
logger.addHandler(cap)
logger.setLevel(logging.DEBUG)
handled = []
real_handle = ch._handle_crash
ch._handle_crash = lambda t, v, tb: handled.append((t, v, tb))
try:
    try:
        raise ValueError("worker boom")
    except ValueError:
        exc = sys.exc_info()
    fake_thread = types.SimpleNamespace(name="Worker-7")
    args = threading.ExceptHookArgs(
        (*exc, fake_thread)) if hasattr(threading, "ExceptHookArgs") else None
    if args is None:
        args = types.SimpleNamespace(
            exc_type=exc[0], exc_value=exc[1], exc_traceback=exc[2],
            thread=fake_thread)
    ch._thread_excepthook(args)
finally:
    ch._handle_crash = real_handle
    logger.removeHandler(cap)
check("crash path was entered", len(handled) == 1, repr(handled))
check("handled exception is the thread's",
      bool(handled) and handled[0][0] is ValueError)
check("log names the thread",
      any("Worker-7" in m for m in cap.messages), repr(cap.messages))
check("log carries the error",
      any("worker boom" in m for m in cap.messages), repr(cap.messages))

print("\ninstall_crash_handler installs both hooks, sys hook unchanged")
before_sys = sys.excepthook
ch.install_crash_handler()
check("threading.excepthook installed",
      threading.excepthook is ch._thread_excepthook)
check("sys.excepthook is the existing handler",
      sys.excepthook is ch._excepthook)
sys.excepthook = before_sys

print("\nrelaunch failure is logged, never raised")
import src.utils.restart as restart_mod
real_restart = restart_mod.restart_app
restart_mod.restart_app = lambda: (_ for _ in ()).throw(
    RuntimeError("exec failed"))
cap2 = Capture()
logger.addHandler(cap2)
try:
    ch._restart_app()  # must not raise
finally:
    restart_mod.restart_app = real_restart
    logger.removeHandler(cap2)
check("relaunch failure logged",
      any("relaunch failed" in m for m in cap2.messages),
      repr(cap2.messages))

print("\nsource: relaunch except:pass is gone")
src = open(os.path.join(os.path.dirname(__file__), "..",
                        "src", "exceptions", "crash_handler.py"),
           encoding="utf-8").read()
body = src.split("def _restart_app", 1)[1].split("\ndef ", 1)[0]
check("_restart_app logs its failure",
      "logger.warning" in body and "except Exception:\n        pass" not in body)

print(f"\nALL {PASS} CHECKS PASSED")
