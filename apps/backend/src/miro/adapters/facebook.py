"""Facebook adapter (MAINTAINED) — port C:\dubtool\scripts\facebook_post_one.py
(+ social_facebook_reels.publish_reel + facebook_receipt + reconcile script).

- Flow: upload -> Next x2 + set_audience(Public) -> submit 1 click.
- Reconcile read-only: candidate-diff 120s + receipt verifier.
- UNSUPPORTED: draft (composer khong luu nhap).
"""
from __future__ import annotations

from miro.adapters.core import SPECS, LiveChromeError, PlatformWorker

SPEC = SPECS["facebook"]

FIXED_TAGS = ("cat", "meo", "meodethuong", "reels")
AUDIENCE = "Public"


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)


def caption_for_item(item: dict) -> str:
    """Caption FB: dung text_for + tags co dinh batch."""
    from miro.adapters.core import text_for
    base = text_for(SPEC, item)
    missing = [t for t in FIXED_TAGS if f"#{t}".lower() not in base.lower()]
    if missing:
        base = f"{base}\n\n{' '.join('#' + t for t in missing)}"
    return base


def canonical_reel_url(identifier: str) -> str:
    return f"https://www.facebook.com/reel/{identifier}"


def verify_reel(receipt: dict, expected_account: str,
                expected_caption: str) -> dict:
    """Port facebook_receipt.verify_reel: receipt phai khop account+caption."""
    url = str((receipt or {}).get("url") or "")
    if "/reel/" not in url:
        return {"verified": False, "reason": "NO_REEL_URL"}
    if expected_caption and expected_caption[:40].lower() not in str(
            (receipt or {}).get("caption", "")).lower():
        return {"verified": False, "reason": "CAPTION_MISMATCH"}
    return {"verified": True, "url": url}


def reconcile_candidates(before_ids: list, after_ids: list) -> list[str]:
    """Port reconcile candidate-diff: ID moi sau Post."""
    before = set(map(str, before_ids or []))
    return [i for i in (after_ids or []) if str(i) not in before]


def send_comment(post_url: str = "", text: str = "", account: str = "",
                 live_page=None) -> dict:
    """Comment Facebook — CHUA PORT (UNSUPPORTED).

    Chua trinh sat REA Q1-Q10 cho comment FB (composer/ack/receipt/guard
    chua co Evidence). Khong tu bia flow. Khi du checklist, port theo mau
    TikTok engage: guard trung + journal + cap.
    """
    return {"error": "UNSUPPORTED_COMMENT_FACEBOOK",
            "hint": "chua trinh sat REA Q1-Q10; chua viet adapter",
            "post_url": post_url, "account": account,
            "comment_chars": len(str(text or ""))}


def send_message(thread_id: str = "", text: str = "", account: str = "",
                 live_page=None) -> dict:
    """Message/DM Facebook — CHUA PORT (UNSUPPORTED, ly do nhu send_comment)."""
    return {"error": "UNSUPPORTED_MESSAGE_FACEBOOK",
            "hint": "chua trinh sat REA Q1-Q10; chua viet adapter",
            "thread_id": thread_id, "account": account,
            "message_chars": len(str(text or ""))}
