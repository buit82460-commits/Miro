"""Facebook adapter (MAINTAINED) — port C:\dubtool\scripts\facebook_post_one.py
(+ social_facebook_reels.publish_reel + facebook_receipt + reconcile script).

- Flow: upload -> Next x2 + set_audience(Public) -> submit 1 click.
- Reconcile read-only: candidate-diff 120s + receipt verifier.
- UNSUPPORTED: draft (composer khong luu nhap).
"""
from __future__ import annotations

from miro.adapters.core import SPECS, PlatformWorker

SPEC = SPECS["facebook"]


def make_worker() -> PlatformWorker:
    return PlatformWorker(SPEC)
