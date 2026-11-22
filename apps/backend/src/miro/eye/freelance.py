"""Eye trinh sat read-only cho 3 site freelance moi.

Chua co adapter post (UNSUPPORTED cho Q4-Q7 toi khi du Q1-Q10). Mat chi doc
actor/url/list/composer qua eye.tab_state — khong click, khong dien form.
"""
from __future__ import annotations

import re
from contextlib import suppress


async def _base(page) -> dict:
    from miro import eye as _eye
    with suppress(Exception):
        return await _eye.tab_state(page) or {}
    return {}


def _actor_from_text(text: str) -> str:
    for pat in (r"@([A-Za-z0-9._]{1,40})",
                r"Xin chao[,\s]+([A-Za-zÀ-ỹ0-9 ._-]{1,60})"):
        hit = re.search(pat, text or "")
        if hit:
            return hit.group(1).strip()
    return ""


async def vlance_record(page) -> dict:
    """Eye vlance.vn: actor + url + co composer dang-viec khong + so job."""
    base = await _base(page)
    text = str(base.get("text") or "")
    url = str(base.get("url") or "")
    return {"platform": "vlance",
            "url": url,
            "actor": _actor_from_text(text),
            "has_composer": "/dang-du-an" in url or "Đăng việc" in text,
            "job_count": (re.search(r"(\d[\d.,]*)\s*(công việc|dự án)",
                                    text) or [None, ""])[1],
            "text_preview": text[:1000]}


async def freelancer_vn_record(page) -> dict:
    """Eye vn.freelancer.com: actor + url + wizard post-project + job count."""
    base = await _base(page)
    text = str(base.get("text") or "")
    url = str(base.get("url") or "")
    return {"platform": "freelancer_vn",
            "url": url,
            "actor": _actor_from_text(text),
            "has_composer": "/post-project" in url or "Tiếp theo" in text,
            "job_count": (re.search(r"([\d,]+)\s*(công việc|jobs?)",
                                    text, re.I) or [None, ""])[1],
            "text_preview": text[:1000]}


async def upwork_record(page) -> dict:
    """Eye upwork.com: actor + role (client/freelancer) + dashboard/post-job."""
    base = await _base(page)
    text = str(base.get("text") or "")
    url = str(base.get("url") or "")
    role = ""
    low = text.lower()
    if "post a job" in low or "talent marketplace" in low:
        role = "client?"
    if "find work" in low or "connects" in low:
        role = (role + "+freelancer?") if role else "freelancer?"
    return {"platform": "upwork",
            "url": url,
            "actor": _actor_from_text(text),
            "role_hint": role,
            "has_composer": "post" in url and "job" in url,
            "text_preview": text[:1000]}
