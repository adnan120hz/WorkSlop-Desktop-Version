"""Reusable stall watchdog for mobilebackup2 backup/restore calls.

Mirrors the Phase 3 watchdog in ``src/restore/restore.py``
(``_restore_protective_backup``): ``mb.backup()`` / ``mb.restore()`` have no
timeout anywhere below them — pymobiledevice3's receive loop only exits when
the device speaks, so a wedged backupd / half-rebooted device / half-open
socket froze the whole operation forever at one percentage with zero status
text (the reported "stuck at 84%").

This helper wraps one such call:

* progress callbacks from the device are tracked (and forwarded verbatim to
  the caller's callback, ``*args``/``**kwargs`` included);
* while waiting, it polls with :func:`asyncio.wait` at a bounded interval
  (``min(20s, stall_seconds / 2)``) and re-emits the last reported progress
  value as a heartbeat so the GUI bar / status text never sits unexplained;
* if no progress arrives for ``stall_seconds`` (env
  ``WORKSLOP_BACKUP_STALL_SECONDS``, default 300), it cancels the wrapped
  task and raises :class:`ConnectionTerminatedError`.

Raising ``ConnectionTerminatedError`` is deliberate: it is already classified
as a retryable connection error by
``src.exceptions.device_errors.is_connection_error`` and by Phase 3's
``is_transient_restore_error``, so the existing bounded retry machinery
(``src.utils.async_retry`` and the Phase 2/3 callers) gets a fresh connection
attempt instead of one immortal hung attempt.
"""

import asyncio
import os
import time
from typing import Any, Awaitable, Callable, Optional, TypeVar

from pymobiledevice3.exceptions import ConnectionTerminatedError

from src.utils.log_util import log_error, log_info

T = TypeVar("T")

#: Environment override for the stall limit (seconds), read at call time so
#: tests and operators can tune it without restarting into a code change.
STALL_ENV_VAR = "WORKSLOP_BACKUP_STALL_SECONDS"
DEFAULT_STALL_SECONDS = 300.0

# Upper bound for the poll interval: even with the default 300s stall limit
# the watchdog wakes (and heartbeats) at least this often.
_MAX_POLL_SECONDS = 20.0


def resolve_stall_seconds(explicit: Optional[float] = None) -> float:
    """Resolve the stall limit: explicit arg > env var > 300s default.

    Non-positive or unparseable values fall back to the default — a watchdog
    that fires instantly (or never, via a nonsensical limit) is worse than
    the documented 300s behaviour.
    """
    candidate = explicit
    if candidate is None:
        raw = os.environ.get(STALL_ENV_VAR, "")
        if raw:
            try:
                candidate = float(raw)
            except (TypeError, ValueError):
                candidate = None
    try:
        value = float(candidate) if candidate is not None else DEFAULT_STALL_SECONDS
    except (TypeError, ValueError):
        return DEFAULT_STALL_SECONDS
    return value if value > 0 else DEFAULT_STALL_SECONDS


async def run_with_stall_watchdog(
    call_factory: Callable[[Callable[..., Any]], Awaitable[T]],
    progress_callback: Optional[Callable[..., Any]] = None,
    *,
    operation: str = "backup",
    stall_seconds: Optional[float] = None,
) -> T:
    """Run one mobilebackup2 call under the stall watchdog.

    ``call_factory`` is a one-argument callable receiving the tracking
    progress callback and returning the awaitable to run, e.g.::

        await run_with_stall_watchdog(
            lambda cb: mb.backup(..., progress_callback=cb),
            progress_callback, operation="backup")

    The caller's ``progress_callback`` receives every device progress value
    verbatim (plus heartbeat re-emits of the last value while the device is
    silent). Returns whatever the wrapped call returns; re-raises its errors
    untouched; raises :class:`ConnectionTerminatedError` when the device
    stops reporting progress for the stall limit.
    """
    stall = resolve_stall_seconds(stall_seconds)
    poll_interval = min(_MAX_POLL_SECONDS, stall / 2) if stall > 0 else _MAX_POLL_SECONDS
    if poll_interval <= 0:  # pragma: no cover - resolve() guarantees > 0
        poll_interval = _MAX_POLL_SECONDS

    state = {"last_progress_at": time.monotonic(), "last_value": None, "seen": False}

    def _tracking_callback(*args, **kwargs):
        state["last_progress_at"] = time.monotonic()
        state["seen"] = True
        if args:
            state["last_value"] = args[0]
        elif "value" in kwargs:
            state["last_value"] = kwargs["value"]
        if progress_callback is not None:
            progress_callback(*args, **kwargs)

    coro = call_factory(_tracking_callback)
    task = asyncio.ensure_future(coro)
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=poll_interval)
            if task.done():
                break
            silent = time.monotonic() - state["last_progress_at"]
            if silent >= stall:
                task.cancel()
                # Drain the cancellation so no orphaned task outlives the
                # raise (and no "exception never retrieved" noise follows).
                try:
                    await task
                except BaseException:
                    pass
                log_error(
                    f"{operation} stalled: no device progress for "
                    f"{silent:.0f}s — aborting this attempt so the retry "
                    f"loop can reconnect (was frozen forever)")
                raise ConnectionTerminatedError(
                    f"Device stopped reporting {operation} progress; "
                    f"retrying with a fresh connection.")
            # Heartbeat: re-emit the last percentage so the GUI bar and
            # status text stay alive with visible signs of waiting.
            if state["seen"] and progress_callback is not None:
                try:
                    progress_callback(state["last_value"])
                except Exception:
                    # A heartbeat must never kill a healthy transfer.
                    pass
            log_info(f"{operation} heartbeat: device silent for "
                     f"{silent:.0f}s (limit {stall:.0f}s)")
    except asyncio.CancelledError:
        task.cancel()
        try:
            await task
        except BaseException:
            pass
        raise
    return await task
