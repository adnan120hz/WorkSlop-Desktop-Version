"""Shared off-GUI-thread runner for manual update checks (Wave 10 fix).

The footer "Check Update" and the Settings "Check for Updates" buttons
share this runner. It exists because the previous hand-rolled pattern in
both places had two lifecycle bugs that crashed on a *second* click
(RuntimeError: Internal C++ object (QThread) already deleted, and
"QObject::setParent: Cannot set parent, new parent is in a different
thread"):

* the result slot was a plain Python closure connected to a signal emitted
  on the worker thread, so the dialog (parented to a main-thread widget)
  was constructed off the GUI thread;
* ``thread.finished`` deleted the QThread with ``deleteLater`` while the
  caller kept a Python reference to it, so the next click called
  ``isRunning()`` on a deleted C++ object.

Contract here:

* fresh QThread + worker per check; repeat clicks while busy are ignored;
* the worker lives in its thread and only emits a signal — it never
  touches a QWidget;
* the result is re-emitted from a slot on this runner (a main-thread
  QObject), so subscribers always run on the GUI thread;
* thread/worker references are dropped in the ``finished`` handler on the
  main thread, never read after deletion.
"""
from PySide6.QtCore import QObject, QThread, Signal


class _UpdateCheckWorker(QObject):
    done = Signal(object)

    def run(self):
        try:
            from src.controllers.web_request_handler import (
                check_for_update, get_update_channel)
            from src.version import App_Version, App_Build
            result = check_for_update(
                App_Version, App_Build, get_update_channel(), force=True)
        except Exception:
            result = None
        self.done.emit(result)


class UpdateCheckRunner(QObject):
    """Runs one update check at a time; ``result_ready`` fires on the
    GUI thread with an ``UpdateCheckResult`` (or None on hard failure)."""

    result_ready = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._worker = None

    @property
    def busy(self) -> bool:
        return self._thread is not None

    def start(self) -> bool:
        """Start a check. Returns False when one is already running."""
        if self._thread is not None:
            return False
        thread = QThread(self)
        worker = _UpdateCheckWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        # _deliver runs on this runner's thread (the GUI thread) because the
        # receiver is a QObject living there — queued delivery, no direct
        # cross-thread widget access.
        worker.done.connect(self._deliver)
        worker.done.connect(thread.quit)
        worker.done.connect(worker.deleteLater)
        thread.finished.connect(self._cleanup)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        thread.start()
        return True

    def _deliver(self, result):
        self.result_ready.emit(result)

    def _cleanup(self):
        # Runs on the GUI thread (the QThread object lives there). Drop the
        # references here — after this point the C++ thread object may be
        # deleted by the queued deleteLater, and nothing may touch it.
        self._thread = None
        self._worker = None
