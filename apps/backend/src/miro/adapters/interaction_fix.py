"""Bang fix tuong tac linh hoat theo platform (rut ra tu test live Profile 16).

TikTok: browser_click timeout tren div custom + placeholder che -> dung
JS click/focus (evaluate). Ref snapshot het han sau re-render -> luu
selector goc [data-e2e="comment-icon"], khong giu ref so.

Facebook: JS click an ngay lan dau; type an ngay; dang bang Enter dispatch.

Instagram: mo panel bang browser_click icon comment; type an ngay;
nut Post nuot click (JS + click thuong) -> bam 2 lan + verify
"nut Post bien mat + text hien trong list", khong verify innerText chung.
"""
from __future__ import annotations

INTERACTION_FIX = {
    "tiktok": {
        "click": "evaluate",
        "click_selectors": ['[data-e2e="comment-icon"]'],
        "type": "focus-then-type",
        "post": "browser_click",
        "verify": "eye-comment-records",
        "notes": "goc [data-e2e]; giu tab focus khi xem video",
    },
    "facebook": {
        "click": "evaluate",
        "click_selectors": ['div[role="button"][aria-label*="Comment"]'],
        "type": "browser_type",
        "post": "enter-dispatch",
        "verify": "innerText-contains",
        "notes": "1 vong JS click -> type -> Enter",
    },
    "instagram": {
        "click": "browser_click-icon",
        "click_selectors": ["comment-icon-button"],
        "type": "browser_type",
        "post": "js-click-then-verify-gone",
        "verify": "post-button-gone-plus-list-contains",
        "notes": "nut Post nuot click; verify nut bien mat + text trong list",
    },
}

CLICK_ORDER = ("evaluate", "browser_click-icon", "browser_click")
POST_ORDER = ("enter-dispatch", "js-click-then-verify-gone", "browser_click")


def click_for(platform: str) -> str:
    return INTERACTION_FIX.get(platform, {}).get("click", "evaluate")


def post_for(platform: str) -> str:
    return INTERACTION_FIX.get(platform, {}).get("post", "browser_click")


def verify_for(platform: str) -> str:
    return INTERACTION_FIX.get(platform, {}).get("verify", "innerText-contains")
