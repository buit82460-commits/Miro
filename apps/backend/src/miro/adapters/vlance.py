"""vLance adapter (MAINTAINED, READ-ONLY recon) — trinh sat Q1-Q10.

Entry: https://www.vlance.vn/ -> /viec-lam-freelance, /freelancers,
composer /dang-du-an (linh vuc/dich vu/tieu de/mo ta + cam contact-info/file
<=10MB/ky nang/han chao gia/loai/hinh thuc/tinh/ngan sach/cong khai).

Q1 actor login, Q3 onboarding OTP/CCCD, Q5 nut Dang viec DOM that, Q6 ack,
Q7 receipt URL sau duyet: cho live Profile 20 (UNSUPPORTED toi khi du).
Post that: UNSUPPORTED (chua du Q1-Q10).
"""
from __future__ import annotations

from miro.adapters.core import SPECS, PlatformWorker

SPEC = {
    "platform": "vlance",
    "origin": "https://www.vlance.vn/",
    "entry": "https://www.vlance.vn/dang-du-an",
}


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)


def job_for(item: dict) -> dict:
    """Chuan hoa job truoc browser: tieu de + mo ta (khong contact-info)."""
    title = str(item.get("title") or "").strip()
    text = str(item.get("description") or item.get("text") or "").strip()
    if not title:
        raise ValueError("MISSING_TITLE")
    if not text:
        raise ValueError("MISSING_DESCRIPTION")
    import re
    if re.search(r"[\w.+-]+@[\w-]+\.\w+|(?:\+?84|0)\d{8,10}",
                 text):
        raise ValueError("SECRET_REJECTED: mo ta chua contact-info "
                         "(khoa vinh vien)")
    return {"title": title, "description": text,
            "budget": item.get("budget"), "skills": item.get("skills") or []}
