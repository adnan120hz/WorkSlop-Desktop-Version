"""The developer credit line shown under the Home brand title.

One builder for all three interfaces so the text and links never
drift apart; each Home passes its own palette (WorkSlop light,
classic light, or Full Nugget dark) so the block stays readable on
every shell. Links are opened by Qt itself (openExternalLinks).

Layout (user order 2026-10-03): a single horizontal row under the
brand title — "Developer Adnan.120hz · TikTok · GitHub ·
Official Website".
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

TIKTOK_URL = "https://www.tiktok.com/@adnan.120hz?_r=1&_t=ZS-9AElXliY2Me"
GITHUB_URL = "https://github.com/adnan120hz"
WEBSITE_URL = "https://adnan120hz.vercel.app"


def credits_html(text_color: str, link_color: str) -> str:
    a = f'<a style="text-decoration:none; color:{link_color}" href='
    sep = f'<span style="color:{text_color}"> · </span>'
    return (
        f'<span style="color:{text_color}">Developer Adnan.120hz</span>'
        f'{sep}{a}"{TIKTOK_URL}">TikTok</a>'
        f'{sep}{a}"{GITHUB_URL}">GitHub</a>'
        f'{sep}{a}"{WEBSITE_URL}">Official Website</a>'
    )


def make_credits_label(parent, text_color: str, link_color: str,
                       align_center: bool = True) -> QLabel:
    lbl = QLabel(parent)
    lbl.setObjectName("brandCredits")
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setOpenExternalLinks(True)
    lbl.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextBrowserInteraction)
    lbl.setWordWrap(False)
    lbl.setText(credits_html(text_color, link_color))
    lbl.setStyleSheet(
        "background: transparent; font-size: 17px; font-weight: 500;")
    if align_center:
        lbl.setAlignment(Qt.AlignCenter)
    return lbl


# Beta tester team block (user order 2026-10-03, corrected twice the
# same day): shown on Home with the credit/attribution text above the
# AutoSave banner. All three names are PLAIN TEXT with no links at all
# (the TikTok links and the Telegram link were both removed by user
# order); Davy is written with his handle as plain text.
BETA_TESTER_NAMES = ("Charlie", "rfrz1d_", "Davy (@Davydavpn)")


def beta_testers_html(text_color: str, link_color: str = "") -> str:
    lines = [
        f'<span style="color:{text_color}; font-weight: 700;">'
        "Beta tester team</span>"
    ]
    for i, name in enumerate(BETA_TESTER_NAMES, 1):
        lines.append(f'<span style="color:{text_color}">{i}. {name}</span>')
    return "<br/>".join(lines)


def make_beta_testers_label(parent, text_color: str, link_color: str = "") -> QLabel:
    lbl = QLabel(parent)
    lbl.setObjectName("betaTesters")
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setWordWrap(True)
    lbl.setText(beta_testers_html(text_color, link_color))
    lbl.setStyleSheet(
        "background: transparent; font-size: 12px; padding: 0 2px;")
    return lbl
