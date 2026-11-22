"""Upwork adapter (MAINTAINED, READ-ONLY recon).

Entry: https://www.upwork.com/i/how-it-works/client/ -> dashboard /home/ ->
wizard post-job 11 buoc (title/skills<=10/scope/budget/desc/files/screening/
preferences/visibility/invite).

Trang chinh + /nx/search/jobs/ bi 403 voi fetch an danh: bat buoc live
Profile 20. Q1 actor/role, Q3 onboarding verify, Q5 nut submit, Q6 ack,
Q7 receipt contract/job URL: UNSUPPORTED toi khi du. Post that: UNSUPPORTED.
"""
from __future__ import annotations

from miro.adapters.core import SPECS, PlatformWorker

SPEC = {
    "platform": "upwork",
    "origin": "https://www.upwork.com/",
    "entry": "https://www.upwork.com/i/how-it-works/client/",
}


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)


def job_for(item: dict) -> dict:
    title = str(item.get("title") or "").strip()
    text = str(item.get("description") or item.get("text") or "").strip()
    if not title:
        raise ValueError("MISSING_TITLE")
    if not text:
        raise ValueError("MISSING_DESCRIPTION")
    skills = item.get("skills") or []
    if len(skills) > 10:
        raise ValueError("TOO_MANY_SKILLS: toi da 10 (khuyen 3-5)")
    return {"title": title, "description": text,
            "budget": item.get("budget"), "skills": list(skills)}
