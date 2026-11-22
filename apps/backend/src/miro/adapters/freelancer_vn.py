"""vn.freelancer.com adapter (MAINTAINED, READ-ONLY recon).

Entry: https://www.vn.freelancer.com/ -> /jobs/ (slug /projects/<skill>/<ten>-<id>)
-> wizard /post-project (prefill ?project_title=) -> /contest/, /freelancers/.

Q1 actor, Q3 onboarding, Q4 field wizard, Q5 nut submit, Q6 ack, Q7 receipt:
cho live Profile 20 (UNSUPPORTED toi khi du). Post that: UNSUPPORTED.
"""
from __future__ import annotations

from miro.adapters.core import SPECS, PlatformWorker

SPEC = {
    "platform": "freelancer_vn",
    "origin": "https://www.vn.freelancer.com/",
    "entry": "https://www.vn.freelancer.com/post-project",
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
    return {"title": title, "description": text,
            "budget": item.get("budget"), "skills": item.get("skills") or []}
