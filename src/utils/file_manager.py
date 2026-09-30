"""Cross-platform "reveal in file manager" helper (WorkSlop Desktop).

After the protective device backup reaches 100%, the GUI calls
:func:`reveal_in_file_manager` with the finished backup directory so the user
can copy it somewhere safe. The file is *selected/highlighted* where the OS
supports it:

- Windows: ``explorer /select,<path>`` (floating window, file highlighted)
- macOS:   ``open -R <path>`` (reveals in Finder)
- Linux:   ``xdg-open <parent dir>`` (opens the folder; per-file selection
  is not portable across file managers)

Never raises: returns False when revealing is impossible so the apply flow
is never interrupted by a file-manager failure.
"""

import logging
import os
import subprocess
import sys

log = logging.getLogger("GoldenNugget.file_manager")


def reveal_in_file_manager(path: str) -> bool:
    """Open the OS file manager showing *path* (file or directory).

    Returns True when the file manager was launched, False otherwise.
    """
    if not path or not os.path.exists(path):
        log.warning("reveal_in_file_manager: path does not exist: %r", path)
        return False
    try:
        if sys.platform == "win32":
            # /select, highlights the file in a new Explorer window.
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            # Linux: open the containing folder (xdg-open has no --select).
            target = path if os.path.isdir(path) else os.path.dirname(path)
            subprocess.Popen(["xdg-open", target])
        return True
    except Exception:
        log.exception("reveal_in_file_manager failed for %r", path)
        return False
