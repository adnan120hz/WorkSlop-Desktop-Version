"""Original Nugget v7.4.1 tweak pages for the third interface (Full Nugget).

These page builders are ports of leminlimez/Nugget v7.4.1's
``src/gui/pages/tools/*.py`` onto the vendored upstream form
(``src/qt/nugget741_ui.py``), so the Full Nugget shell shows Nugget's
own dark layout, rows and Default/Enabled/Disabled tri-state radio
controls instead of this app's iOS-style pages. Only the bindings are
adapted: controls drive this repo's tweak objects (the WorkSlop v4
verbatim set everywhere except Liquid Glass, which drives the
100%-original Nugget set from ``src/tweaks/nugget_lg.py``), and rows
whose tweak this app has tombstoned are hidden rather than left dead.
The page host/glue lives in ``src/gui/main_window.py``.
"""
from .liquidglass import NuggetLiquidGlassPage
from .springboard import NuggetSpringboardPage
from .internal import NuggetInternalPage
from .status_bar import NuggetStatusBarPage

__all__ = [
    "NuggetLiquidGlassPage",
    "NuggetSpringboardPage",
    "NuggetInternalPage",
    "NuggetStatusBarPage",
]
