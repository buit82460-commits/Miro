"""Shopee adapter (MAINTAINED, BLOCKED live) —
port C:\dubtool\scripts\shopee_post_one.py.

- product_for: name + price>0 int + stock>=0 + desc<=3000 + images<=9.
- Seller Centre fill form -> Save -> readback tim ten <=120s.
- BLOCKED: onboarding Seller Centre 1/5 (thieu dia chi + SDT) -> KHONG test
  live; huong research la shopee.vn affiliate (search/san pham/danh gia/gia).
- UNSUPPORTED: delete, draft.
"""
from __future__ import annotations

from pathlib import Path

from miro.adapters.core import SPECS, LiveChromeError, PlatformWorker

SPEC = SPECS["shopee"]
MAX_IMAGES = 9


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)


def validate_product(item: dict) -> list[str]:
    """Validate product truoc browser: images + file ton tai."""
    from miro.adapters.core import text_for
    problems = []
    try:
        text_for(SPEC, item)
    except ValueError as exc:
        problems.append(str(exc)[:120])
    images = item.get("images") or []
    if item.get("local_path") and str(item.get("local_path")) not in images:
        images = [str(item.get("local_path")), *images]
    if len(images) > MAX_IMAGES:
        problems.append(f"qua {MAX_IMAGES} anh")
    for img in images[:MAX_IMAGES]:
        if not Path(str(img)).exists():
            problems.append(f"MEDIA_UNVERIFIED: {img}")
            break
    return problems


def update_profile(name: str = "", description: str = "",
                   account: str = "") -> dict:
    """Port update_profile (live tren Seller Centre; offline mo ta)."""
    return {"account": account, "name": name, "description": description,
            "update": "LIVE_ONLY",
            "hint": "chay tren page that qua live.LivePage"}


def read_orders(account: str = "") -> dict:
    """Port read_orders (read-only)."""
    return {"account": account, "orders": "LIVE_ONLY",
            "runtime": "table tbody tr, [data-order-id]",
            "hint": "read-only; chay tren page that"}


def research_product(url: str = "") -> dict:
    """Huong moi (AGENTS Shopee): research shopee.vn affiliate, KHONG ban shop."""
    return {"url": url, "runtime": "shopee.vn search/trang san pham/danh gia/gia",
            "hint": "read-only affiliate research; khong Seller onboarding"}
