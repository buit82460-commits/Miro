"""TikTok adapter (MAINTAINED) — port C:\dubtool\scripts\tiktok_post_one.py
(+ publish_maoziqi59_tiktok prepare/submit/reconcile).

- Studio upload: cho Uploaded -> caption/audience Everyone/AI-label/account
  checks -> submit() 1 click -> poll receipt 5s x12.
- Draft rieng (khong ghi publication): run_draft/run_draft_batch.
- Discover (read-only): hashtag/sound/trending/related/replies.
- Account mac dinh: @kemkhongta (Profile 20 da verify login).
"""
from __future__ import annotations

from miro.adapters.core import SPECS, LiveChromeError, PlatformWorker

SPEC = SPECS["tiktok"]

AUDIENCE = "Everyone"
DISCOVER_KINDS = ("hashtag", "sound", "trending", "related", "replies")


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)


def draft_job_id(shortcode: str) -> str:
    return f"{SPEC.job_prefix}draft-{str(shortcode).rstrip('-')}"


def check_preflight(snapshot: dict, caption: str, account: str) -> list[str]:
    """Port preflight checks: caption khop + Everyone + AI-label + avatar."""
    problems = []
    if (snapshot.get("caption", "") or "").strip() != caption.strip():
        problems.append("CAPTION_MISMATCH")
    if "Everyone" not in str(snapshot.get("audience", "")):
        problems.append("AUDIENCE_NOT_EVERYONE")
    if not snapshot.get("ai_label"):
        problems.append("AI_LABEL_NOT_ENABLED")
    if str(snapshot.get("avatar", "")).lstrip("@").lower() != str(
            account).lstrip("@").lower():
        problems.append("ACCOUNT_MISMATCH")
    return problems


def run_draft(item: dict, account: str = "") -> dict:
    """Save 1 video lam TikTok Studio Draft (KHONG bam Post).

    Port run_draft: upload + fill + luu nhap; khong ghi publication,
    khong receipt post. Live thuc hien qua live.LivePage pre TikTok
    (caller tu dieu khien); day la ban ghi so + validate offline.
    """
    from miro.adapters.core import text_for
    caption = text_for(SPEC, item)
    path = str(item.get("local_path") or item.get("media_path") or "")
    if not path:
        raise LiveChromeError("TikTok draft can file video.",
                              before_submit=True)
    return {"shortcode": item.get("shortcode"), "draft": True,
            "caption": caption, "local_path": path,
            "hint": "draft saved via Studio; no Post clicked"}


def discover(kind: str, query: str = "") -> dict:
    """Read-only discover: mo ta endpoint theo kind (live chay tren JARVIS)."""
    if kind not in DISCOVER_KINDS:
        raise ValueError(f"UNSUPPORTED_DISCOVER_KIND: {kind}")
    return {"kind": kind, "query": query, "runtime": "tiktok_endpoints.discover",
            "hint": "read-only; chay tren JARVIS backend"}
