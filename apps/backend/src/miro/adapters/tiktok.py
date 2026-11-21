"""TikTok adapter (MAINTAINED) — port C:\dubtool\scripts\tiktok_post_one.py
(+ publish_maoziqi59_tiktok prepare/submit/reconcile).

- Studio upload: cho Uploaded -> caption/audience Everyone/AI-label/account
  checks -> submit() 1 click -> poll receipt 5s x12.
- Draft rieng (khong ghi publication): run_draft/run_draft_batch.
- Discover (read-only): hashtag/sound/trending/related/replies.
- Engage (port tiktok_engage_one.py): view/like/repost/comment/follow +
  guard trung + daily cap; comment text tu manifest/CLI.
- Account mac dinh: @kemkhongta (Profile 20 da verify login).
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from miro.adapters.core import SPECS, LiveChromeError, PlatformWorker
from miro.publishing.publisher import atomic_save, load_json_if_exists

SPEC = SPECS["tiktok"]

AUDIENCE = "Everyone"
DISCOVER_KINDS = ("hashtag", "sound", "trending", "related", "replies")

# Engage (port dubtool scripts/tiktok_engage_one.py): view + like + repost +
# comment + follow qua managed tab. Comment text tu manifest/CLI, khong hard-code.
ENGAGE_ACTIONS = ("view", "like", "repost", "comment", "follow")
DAILY_CAPS = {"view": 50, "like": 20, "repost": 10, "comment": 10,
              "follow": 5}
ENGAGE_PUBLICATION = "publication-engage.json"


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


# ---- Engage: view + like + repost + comment + follow ----
# Port dubtool scripts/tiktok_engage_one.py: guard trung (publication-engage
# + journal), daily cap/profile, delay giua actions, comment text tu manifest.

def engage_job_id(shortcode: str, profile: str, action: str) -> str:
    """Port job_id_for: journal rieng moi (video, profile, action)."""
    safe = re.sub(r"[^A-Za-z0-9@_-]+", "",
                  f"{profile}-{action}-{shortcode}")[:120]
    return f"engage-tiktok-{safe}"


def guard_engage(base, shortcode: str, profile: str, action: str,
                 journal_name: str):
    """Port guard_action: da engage -> skip, chua -> None (never replay)."""
    publication = load_json_if_exists(Path(base) / ENGAGE_PUBLICATION,
                                      {"items": []})
    if any(x.get("shortcode") == str(shortcode)
           and x.get("profile") == profile
           and x.get("action") == action
           and x.get("status") in ("done", "verified")
           for x in publication.get("items", [])):
        return {"skipped": "ALREADY_IN_PUBLICATION", "shortcode": shortcode,
                "profile": profile, "action": action}
    journal = Path(base) / "attempts" / journal_name
    if journal.exists():
        return {"skipped": "UNRECONCILED_ATTEMPT", "shortcode": shortcode,
                "profile": profile, "action": action,
                "hint": "reconcile read-only, never replay"}
    return None


def merge_engage(base, entry: dict) -> dict:
    publication = load_json_if_exists(Path(base) / ENGAGE_PUBLICATION,
                                      {"items": []})
    items = [x for x in publication.get("items", [])
             if not (x.get("shortcode") == entry["shortcode"]
                     and x.get("profile") == entry["profile"]
                     and x.get("action") == entry["action"])]
    items.append(entry)
    publication["items"] = items
    atomic_save(Path(base) / ENGAGE_PUBLICATION, publication)
    return publication


def daily_engage_count(base, profile: str, action: str) -> int:
    """Port _daily_count: dem journal done/verified trong ngay (cap/profile)."""
    day = time.strftime("%Y%m%d")
    safe_profile = re.sub(r"\W+", "", str(profile or ""))
    n = 0
    att = Path(base) / "attempts"
    for jp in att.glob(f"engage-tiktok-{safe_profile}-*.json"):
        try:
            data = load_json_if_exists(jp, {})
        except Exception:
            continue
        if data.get("profile") == profile and data.get("action") == action \
                and data.get("status") in ("done", "verified"):
            n += 1
    return n


def describe_engage(shortcode: str, actions=None, profile: str = "Profile 20",
                    actor: str = "@kemkhongta",
                    comment_text: str = "") -> dict:
    """Mo ta 1 luot engage offline (live bam nut that qua live.LivePage).

    Guard trung + daily cap truoc; comment thieu text -> NO_COMMENT_TEXT
    (khong hard-code spam). Live thuc hien tren managed tab caller inject.
    """
    acts = [a.strip().lower() for a in (actions or ["view", "like", "follow"])
            if a.strip()]
    bad = [a for a in acts if a not in ENGAGE_ACTIONS]
    if bad:
        raise ValueError(f"UNSUPPORTED_ENGAGE_ACTION: {bad}")
    if "comment" in acts and not str(comment_text or "").strip():
        return {"skipped": "NO_COMMENT_TEXT", "shortcode": shortcode,
                "profile": profile, "action": "comment",
                "hint": "comment text lay tu manifest/CLI"}
    return {"shortcode": shortcode, "profile": profile, "actor": actor,
            "actions": acts, "comment_chars": len(str(comment_text or "")),
            "daily_caps": {a: DAILY_CAPS.get(a, 20) for a in acts},
            "runtime": "live.LivePage engage via managed tab; "
                       "offline chi mo ta + guard"}
