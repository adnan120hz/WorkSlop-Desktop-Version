"""The developer credit block shown under the Home brand title.

One builder for all three interfaces so the text and links never
drift apart; each Home passes its own palette (WorkSlop light,
classic light, or Full Nugget dark) so the block stays readable on
every shell. Links are opened by Qt itself (openExternalLinks).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

TIKTOK_URL = "https://www.tiktok.com/@adnan.120hz?_r=1&_t=ZS-9AElXliY2Me"
GITHUB_URL = "https://github.com/adnan120hz"
WEBSITE_URL = "https://adnan120hz.vercel.app"


def credits_html(text_color: str, link_color: str) -> str:
    a = f'<a style="text-decoration:none; color:{link_color}" href='
    return (
        f'<span style="color:{text_color}">Developer Adnan.120hz</span><br/>'
        f'<span style="color:{text_color}">TikTok: </span>'
        f'{a}"{TIKTOK_URL}">@adnan.120hz</a><br/>'
        f'<span style="color:{text_color}">GitHub Aku adnan.120hz: </span>'
        f'{a}"{GITHUB_URL}">github.com/adnan120hz</a><br/>'
        f'<span style="color:{text_color}">'
        f'Official Website Adnan.120hz: </span>'
        f'{a}"{WEBSITE_URL}">adnan120hz.vercel.app</a>'
    )


def make_credits_label(parent, text_color: str, link_color: str,
                       align_center: bool = True) -> QLabel:
    lbl = QLabel(parent)
    lbl.setObjectName("brandCredits")
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setOpenExternalLinks(True)
    lbl.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextBrowserInteraction)
    lbl.setText(credits_html(text_color, link_color))
    lbl.setStyleSheet("background: transparent; font-size: 13px;")
    if align_center:
        lbl.setAlignment(Qt.AlignCenter)
    return lbl
