"""Cross-platform application restart.

``os.exec*`` does not exist on Windows, so the old ``os.execl`` calls
(preset loading, crash recovery) crashed or silently did nothing there.
This helper is the single supported way to relaunch WorkSlop Desktop:

- Windows: spawn a detached copy of the current process, then exit.
- macOS/Linux: ``os.execl`` replaces the current process in place.
- Frozen (PyInstaller): relaunch the bundled executable itself.
"""

import os
import subprocess
import sys


def restart_app() -> None:
    """Relaunch WorkSlop Desktop with the same arguments, then exit.

    Never returns on success: on POSIX the process image is replaced, on
    Windows the current process exits after spawning its replacement.
    """
    argv = list(sys.argv)
    if getattr(sys, "frozen", False):
        command = [sys.executable] + argv[1:]
    else:
        command = [sys.executable] + argv
    if sys.platform == "win32":
        subprocess.Popen(
            command,
            creationflags=(
                subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP
            ),
            close_fds=True,
        )
        os._exit(0)
    os.execl(sys.executable, sys.executable, *argv)
