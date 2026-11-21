"""Shopee adapter (MAINTAINED, BLOCKED live) —
port C:\dubtool\scripts\shopee_post_one.py.

- product_for: name + price>0 int + stock>=0 + desc<=3000 + images<=9.
- Seller Centre fill form -> Save -> readback tim ten <=120s.
- BLOCKED: onboarding Seller Centre 1/5 (thieu dia chi + SDT) -> KHONG test
  live; huong research la shopee.vn affiliate (search/san pham/danh gia/gia).
- UNSUPPORTED: delete, draft.
"""
from __future__ import annotations

from miro.adapters.core import SPECS, PlatformWorker

SPEC = SPECS["shopee"]


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)
